import html

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.services import gemini, image_prep
from src.services import premium as premium_svc
from src.states.flows import SerialAuditFlow

router = Router()
MAX_PHOTOS = 5


async def _serial_allowed(user_id: int) -> bool:
    """Serial multi-photo analysis is Premium-only (avoids free multi-Gemini abuse)."""
    return await premium_svc.is_premium(user_id)


def _serial_kb(count: int) -> InlineKeyboardMarkup:
    rows = []
    if count < MAX_PHOTOS:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📸 Добавить ещё ({count}/{MAX_PHOTOS})", callback_data="serial_add_hint"
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"✅ Анализировать все {count} фото", callback_data="serial_done"
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="serial_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "start_serial")
async def start_serial(callback: CallbackQuery, state: FSMContext):
    if not await _serial_allowed(callback.from_user.id):
        await callback.answer(
            "Серийный анализ доступен только с Premium.",
            show_alert=True,
        )
        return
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
async def collect_photo(message: Message, state: FSMContext, bot: Bot):
    if not await _serial_allowed(message.from_user.id):
        await state.clear()
        await message.answer("⚠️ Серийный анализ доступен только с Premium.")
        return

    data = await state.get_data()
    photos = data.get("photos", [])

    if len(photos) >= MAX_PHOTOS:
        await message.answer(
            f"⚠️ Максимум {MAX_PHOTOS} фото. Нажми «Анализировать».",
            reply_markup=_serial_kb(len(photos)),
        )
        return

    wait = await message.answer("🔎 Проверяю качество снимка...")
    file_io = await bot.download(message.photo[-1])
    raw_bytes = file_io.read()
    data_bytes, _ = await image_prep.prepare_image_async(raw_bytes, "image/jpeg")
    qc = await gemini.check_quality(data_bytes)

    if not qc["ok"]:
        raw_tip = qc.get("tip")
        tip = f"\n💡 {html.escape(str(raw_tip))}" if raw_tip else ""
        reason = html.escape(str(qc.get("reason", "Качество недостаточно")))
        score = html.escape(str(qc.get("score", 0)))
        await wait.edit_text(
            f"❌ <b>Снимок не принят</b> <code>{score}/100</code>\n\n"
            f"📋 {reason}"
            f"{tip}\n\nПересними и отправь снова 👇"
        )
        return

    file_id = message.photo[-1].file_id
    photos.append(file_id)
    await state.update_data(photos=photos)
    score_emoji = "🟢" if qc["verdict"] == "ПРИНЯТО" else "🟡"
    score = html.escape(str(qc.get("score", 0)))
    await wait.edit_text(
        f"{score_emoji} Снимок {len(photos)}/{MAX_PHOTOS} принят <code>{score}/100</code>",
        reply_markup=_serial_kb(len(photos)),
    )


@router.callback_query(F.data == "serial_add_hint", SerialAuditFlow.collecting)
async def serial_add_hint(callback: CallbackQuery):
    await callback.answer("Просто отправь следующее фото в чат", show_alert=False)


@router.callback_query(F.data == "serial_done", SerialAuditFlow.collecting)
async def serial_done(callback: CallbackQuery, state: FSMContext):
    if not await _serial_allowed(callback.from_user.id):
        await state.clear()
        await callback.answer("Серийный анализ доступен только с Premium.", show_alert=True)
        return

    data = await state.get_data()
    photos = data.get("photos", [])

    if not photos:
        await callback.answer("Нет фото для анализа!", show_alert=True)
        return

    await callback.message.edit_text(f"⏳ Анализирую {len(photos)} фото...")
    results = []
    locale = "ru"

    risk_icon = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}
    for i, file_id in enumerate(photos, 1):
        try:
            file = await callback.bot.get_file(file_id)
            bio = await callback.bot.download_file(file.file_path)
            raw_bytes = bio.read() if hasattr(bio, "read") else bytes(bio)
            data_bytes, _ = await image_prep.prepare_image_async(raw_bytes, "image/jpeg")

            analysis = await gemini.analyze_photo(data_bytes, locale=locale)
            risk = html.escape(str(analysis.get("risk_level", "?")))
            obj = html.escape(str(analysis.get("object_type", "объект")))
            verdict = html.escape(str((analysis.get("free_verdict") or "")[:200]))
            icon = risk_icon.get(analysis.get("risk_level"), "⚪")
            results.append(
                f"📸 <b>Фото {i}</b> — {obj}\n{icon} Риск: <b>{risk}</b>\n<i>{verdict}</i>"
            )
        except Exception as e:
            results.append(f"📸 Фото {i}: ошибка — {html.escape(str(e))}")

    header = f"📊 <b>Серийный анализ — {len(photos)} фото</b>\n\n"
    footer = "\n\n<i>Для детального отчёта по каждому снимку отправляйте фото по одному.</i>"
    base_len = len(header) + len(footer) + 50

    summary_items: list[str] = []
    total_len = 0
    truncated = False
    for res in results:
        if total_len + len(res) + 2 + base_len > 4000:
            truncated = True
            break
        summary_items.append(res)
        total_len += len(res) + 2

    summary = "\n\n".join(summary_items)
    if truncated:
        summary += "\n\n<i>... [часть результатов скрыта из-за лимита длины]</i>"

    text = f"{header}{summary}{footer}"
    await callback.message.edit_text(text, parse_mode="HTML")
    await state.clear()


@router.callback_query(F.data == "serial_cancel")
async def serial_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Серийный анализ отменён.")
    await callback.answer()
