from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.services import gemini
from src.states.flows import SerialAuditFlow

router = Router()
MAX_PHOTOS = 5


def _serial_kb(count: int) -> InlineKeyboardMarkup:
    rows = []
    if count < MAX_PHOTOS:
        rows.append([InlineKeyboardButton(
            text=f"📸 Добавить ещё ({count}/{MAX_PHOTOS})",
            callback_data="serial_add_hint"
        )])
    rows.append([InlineKeyboardButton(
        text=f"✅ Анализировать все {count} фото",
        callback_data="serial_done"
    )])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="serial_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "start_serial")
async def start_serial(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SerialAuditFlow.collecting)
    await state.update_data(photos=[])
    await callback.message.answer(
        f"📸 <b>Серийный анализ</b>\n\n"
        f"Отправляй фото тепловизора по одному (до {MAX_PHOTOS} штук).\n"
        f"Я проанализирую все вместе и дам общий отчёт.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SerialAuditFlow.collecting, F.photo)
async def collect_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"⚠️ Максимум {MAX_PHOTOS} фото. Нажми «Анализировать».",
            reply_markup=_serial_kb(len(photos)),
        )
        return

    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    await message.answer(
        f"✅ Фото {len(photos)}/{MAX_PHOTOS} добавлено.",
        reply_markup=_serial_kb(len(photos)),
    )


@router.callback_query(F.data == "serial_add_hint", SerialAuditFlow.collecting)
async def serial_add_hint(callback: CallbackQuery):
    await callback.answer("Просто отправь следующее фото в чат", show_alert=False)


@router.callback_query(F.data == "serial_done", SerialAuditFlow.collecting)
async def serial_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])

    if not photos:
        await callback.answer("Нет фото для анализа!", show_alert=True)
        return

    await callback.message.edit_text(f"⏳ Анализирую {len(photos)} фото...")
    results = []
    locale = "ru"

    for i, file_id in enumerate(photos, 1):
        try:
            file = await callback.bot.get_file(file_id)
            bio = await callback.bot.download_file(file.file_path)
            data_bytes = bio.read() if hasattr(bio, "read") else bytes(bio)

            qc = await gemini.check_quality(data_bytes)
            if not qc.get("ok"):
                results.append(f"📸 <b>Фото {i}</b>: ❌ {qc.get('reason', 'низкое качество')}")
                continue

            analysis = await gemini.analyze_photo(data_bytes, locale=locale)
            risk = analysis.get("risk_level", "?")
            obj = analysis.get("object_type", "объект")
            verdict = (analysis.get("free_verdict") or "")[:200]
            icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(risk, "⚪")
            results.append(
                f"📸 <b>Фото {i}</b> — {obj}\n"
                f"{icon} Риск: <b>{risk}</b>\n"
                f"<i>{verdict}</i>"
            )
        except Exception as e:
            results.append(f"📸 Фото {i}: ошибка — {e}")

    summary = "\n\n".join(results)
    text = (
        f"📊 <b>Серийный анализ — {len(photos)} фото</b>\n\n"
        f"{summary}\n\n"
        f"<i>Для детального отчёта по каждому снимку отправляйте фото по одному.</i>"
    )
    if len(text) > 4000:
        text = text[:3950] + "\n\n...</i>"

    await callback.message.edit_text(text, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "serial_cancel")
async def serial_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Серийный анализ отменён.")
    await callback.answer()
