import asyncio
import hashlib
import logging
from datetime import UTC, date

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Contact,
    InlineKeyboardButton,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.config import settings
from src.keyboards.menus import (
    BTN_CALC,
    BTN_CALC_EN,
    BTN_PHOTO,
    BTN_PHOTO_EN,
    BTN_PHOTO_PREM,
    BTN_PHOTO_PREM_EN,
    BTN_UPGRADE,
    BTN_UPGRADE_EN,
    client_menu,
    contact_kb,
    heating_kb,
    order_kb,
)
from src.services import gemini, image_prep, metrics, odoo, roles
from src.services import premium as premium_svc
from src.services import referral as ref_svc
from src.services.album_buffer import MAX_FRAMES as ALBUM_MAX_FRAMES
from src.services.album_buffer import AlbumBuffer
from src.services.comparison import format_comparison
from src.services.i18n import t
from src.services.redis import (
    cache_analysis,
    get_cached_analysis,
    get_last_analysis,
    get_last_report,
    save_last_analysis,
    save_last_report,
    save_webapp_data,
    schedule_reminder,
)
from src.states.flows import AuditFlow, CalcFlow, LeadFlow
from src.utils import typing_loop

logger = logging.getLogger(__name__)
router = Router(name="client")

_SEP = "━━━━━━━━━━━━━━━━━━━━━"


def _supervise_task(task: asyncio.Task, *, name: str) -> None:
    """Attach a done-callback so a fire-and-forget task never fails silently.

    Background persistence (Odoo report save, reminder scheduling) runs detached
    so the user's reply is not delayed by Odoo latency. Without supervision an
    exception inside such a task is swallowed by the event loop and the data is
    lost while the user's quota was already charged. The callback logs the
    traceback and bumps a metric so the loss is observable (alertable), not mute.
    """

    def _on_done(t: asyncio.Task) -> None:
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            metrics.inc("background_task_failures_total", {"task": name})
            logger.error("background task %r failed: %s", name, exc, exc_info=exc)

    task.add_done_callback(_on_done)


# ── Photo Audit ───────────────────────────────────────────────────────────────


@router.message(F.text.in_({BTN_PHOTO, BTN_PHOTO_EN, BTN_PHOTO_PREM, BTN_PHOTO_PREM_EN}))
async def audit_start(
    message: Message,
    state: FSMContext,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.set_state(AuditFlow.photo)
    await state.update_data(locale=locale, is_local=is_local)
    await message.answer(t("audit_prompt", locale))


_MAX_PHOTO_BYTES = 20 * 1024 * 1024  # 20 MB — Gemini hard limit

# MIME types accepted from image documents (subset Gemini Vision supports).
_SUPPORTED_DOC_MIME = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
)


async def _check_quota(
    message: Message, user_id: int, locale: str, is_local: bool
) -> tuple[bool, bool, bool]:
    """Resolve premium/quota state for an audit request.

    Returns ``(allowed, is_prem, used_bonus)``. When ``allowed`` is False the
    upgrade/limit message has already been sent to the user.

    TODO(quota-toctou): this still uses the non-atomic check (``scans_remaining``
    here) + later charge (``increment_scan`` in ``_analyze_and_reply``). Two
    concurrent photos can both pass the check before either increments, briefly
    overrunning ``free_daily_scans``. An atomic, race-free primitive now exists —
    ``premium.consume_scan`` (INCR-reserve + rollback) — but wiring it in changes
    the "charge only after a *successful* analysis" semantics (a failed Gemini
    call would consume the slot) and would need a refund-on-failure path plus a
    rewrite of the quota tests. Deferred to keep prod green; see premium.py.
    """
    is_prem = await premium_svc.is_premium(user_id)
    used_bonus = False

    if not is_prem:
        remaining = await premium_svc.scans_remaining(user_id)
        if remaining <= 0:
            used_bonus = await ref_svc.consume_bonus_scan(user_id)
            if not used_bonus:
                upgrade_b = InlineKeyboardBuilder()
                if locale == "ru":
                    upgrade_b.row(
                        InlineKeyboardButton(
                            text=f"⭐️ Premium — {settings.premium_price_stars} Stars/мес",
                            callback_data="premium:buy",
                        )
                    )
                    upgrade_b.row(
                        InlineKeyboardButton(
                            text="🎁 Пригласить друга (+5 сканов)",
                            callback_data="action:invite",
                        )
                    )
                    await message.answer(
                        f"⚠️ <b>Дневной лимит исчерпан</b>\n"
                        f"──────────────────────\n"
                        f"📊 Использовано: <b>{settings.free_daily_scans}/{settings.free_daily_scans}</b> анализов\n"
                        f"🕐 Лимит обновится в <b>00:00 UTC</b>\n\n"
                        "<b>Как продолжить прямо сейчас:</b>\n"
                        "  ⭐️ Premium — безлимитный анализ\n"
                        "  🎁 Пригласите друга — получите +5 бонусных сканов",
                        reply_markup=upgrade_b.as_markup(),
                    )
                else:
                    upgrade_b.row(
                        InlineKeyboardButton(
                            text=f"⭐️ Premium — {settings.premium_price_stars} Stars/month",
                            callback_data="premium:buy",
                        )
                    )
                    upgrade_b.row(
                        InlineKeyboardButton(
                            text="🎁 Invite a Friend (+5 scans)",
                            callback_data="action:invite",
                        )
                    )
                    await message.answer(
                        f"⚠️ <b>Daily limit reached</b>\n"
                        f"──────────────────────\n"
                        f"📊 Used: <b>{settings.free_daily_scans}/{settings.free_daily_scans}</b> analyses\n"
                        f"🕐 Limit resets at <b>00:00 UTC</b>\n\n"
                        "<b>Continue right now:</b>\n"
                        "  ⭐️ Premium — unlimited analysis\n"
                        "  🎁 Invite a friend — earn +5 bonus scans",
                        reply_markup=upgrade_b.as_markup(),
                    )
                return False, is_prem, used_bonus

    return True, is_prem, used_bonus


async def _flush_album(
    media_group_id: str,
    frames: list[dict],
    context: dict,
    overflow: bool,
) -> None:
    """Process a buffered album as ONE analysis (one quota charge, one reply).

    ``frames`` items are ``{"raw": bytes, "mime": str}`` (raw downloaded bytes;
    photos use image/jpeg). Runs quota once, downscales each frame, then routes
    through the shared :func:`_analyze_and_reply` pipeline with all frames.
    Any failure is contained so the bot never crashes (logged).
    """
    message: Message = context["message"]
    bot: Bot = context["bot"]
    locale: str = context.get("locale", "ru")
    is_local: bool = context.get("is_local", True)
    voice_context: str = context.get("voice_context", "")
    state: FSMContext | None = context.get("state")
    user_id = message.from_user.id

    if overflow:
        note = (
            f"ℹ️ В альбоме больше {ALBUM_MAX_FRAMES} фото — анализирую первые {ALBUM_MAX_FRAMES}."
            if locale == "ru"
            else f"ℹ️ Album has more than {ALBUM_MAX_FRAMES} photos — analyzing the first {ALBUM_MAX_FRAMES}."
        )
        await message.answer(note)

    allowed, is_prem, used_bonus = await _check_quota(message, user_id, locale, is_local)
    if not allowed:
        # Quota exhausted — keep AuditFlow.photo so the album can be resent after
        # upgrading; do NOT clear state here.
        return
    # Quota OK: this album will be processed → release the FSM state now.
    if state is not None:
        await state.clear()

    metrics.inc("photo_input_total", {"kind": "album"})
    await bot.send_chat_action(message.chat.id, "upload_photo")
    wait = await message.answer(t("analyzing", locale))
    _typing = asyncio.create_task(typing_loop(bot, message.chat.id))
    try:
        prepared: list[tuple[bytes, str]] = [
            await image_prep.prepare_image_async(f["raw"], f["mime"]) for f in frames
        ]
        await _analyze_and_reply(
            message,
            bot,
            wait=wait,
            typing_task=_typing,
            frames=prepared,
            locale=locale,
            is_local=is_local,
            is_prem=is_prem,
            used_bonus=used_bonus,
            voice_context=voice_context,
        )
    except Exception:
        # Preprocessing or analysis blew up. Stop typing, drop the placeholder,
        # and tell the user plainly — but DON'T swallow the log (re-raise so the
        # AlbumBuffer logs the traceback for diagnostics).
        _typing.cancel()
        try:
            await wait.delete()
        except Exception:
            logger.debug("could not delete album 'analyzing' placeholder", exc_info=True)
        err = (
            "⚠️ Не удалось обработать альбом, попробуйте ещё раз."
            if locale == "ru"
            else "⚠️ Could not process the album, please try again."
        )
        try:
            await message.answer(err, reply_markup=client_menu(locale, is_local))
        except Exception:
            logger.debug("could not send album error notice", exc_info=True)
        raise


# Module-level album buffer (one asyncio loop → no locks needed).
_album_buffer = AlbumBuffer(_flush_album, max_frames=ALBUM_MAX_FRAMES)


async def _buffer_album_frame(
    message: Message,
    state: FSMContext,
    bot: Bot,
    *,
    raw: bytes,
    mime: str,
) -> None:
    """Add one album frame to the debounced buffer.

    Context (locale/is_local/voice/message/bot/state) is captured from the FIRST
    frame. FSM state is NOT cleared here — it stays in AuditFlow.photo so every
    frame of the group keeps matching the audit handlers; it is cleared once at
    flush time."""
    data = await state.get_data()
    locale: str = data.get("locale", "ru")
    is_local: bool = data.get("is_local", True)
    voice_context: str = data.get("voice_context", "")
    _album_buffer.add(
        message.media_group_id,
        {"raw": raw, "mime": mime},
        {
            "message": message,
            "bot": bot,
            "state": state,
            "locale": locale,
            "is_local": is_local,
            "voice_context": voice_context,
        },
    )


@router.message(AuditFlow.photo, F.photo)
async def audit_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if getattr(message, "media_group_id", None):
        # Capacity gate BEFORE download: never pull bytes for frames we'd drop.
        if not _album_buffer.can_accept(message.media_group_id):
            return  # group already at max_frames; overflow flagged for flush notice
        photo = message.photo[-1]
        if photo.file_size and photo.file_size > _MAX_PHOTO_BYTES:
            return  # skip oversized frame silently; rest of album still analyzed
        file_io = await bot.download(photo)
        await _buffer_album_frame(message, state, bot, raw=file_io.read(), mime="image/jpeg")
        return

    data = await state.get_data()
    locale: str = data.get("locale", "ru")
    is_local: bool = data.get("is_local", True)

    user_id = message.from_user.id
    allowed, is_prem, used_bonus = await _check_quota(message, user_id, locale, is_local)
    if not allowed:
        # Keep AuditFlow.photo so that after buying Premium / inviting a friend
        # the user can resend the photo without re-entering the menu.
        return
    await state.clear()

    metrics.inc("photo_input_total", {"kind": "photo"})
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > _MAX_PHOTO_BYTES:
        err = (
            "⚠️ Фото слишком большое (максимум 20 МБ). Отправьте снимок меньшего размера."
            if locale == "ru"
            else "⚠️ Photo is too large (max 20 MB). Please send a smaller image."
        )
        await message.answer(err, reply_markup=client_menu(locale, is_local))
        return

    await bot.send_chat_action(message.chat.id, "upload_photo")
    wait = await message.answer(t("analyzing", locale))
    _typing = asyncio.create_task(typing_loop(bot, message.chat.id))
    try:
        file_io = await bot.download(photo)
        photo_bytes = file_io.read()
    except Exception:
        _typing.cancel()
        await wait.delete()
        raise

    await _analyze_and_reply(
        message,
        bot,
        wait=wait,
        typing_task=_typing,
        frames=[(photo_bytes, "image/jpeg")],
        locale=locale,
        is_local=is_local,
        is_prem=is_prem,
        used_bonus=used_bonus,
        voice_context=data.get("voice_context", ""),
    )


async def _cached_analyze(frames: list[tuple[bytes, str]], locale: str, voice_context: str) -> dict:
    """Combined cache lookup + Gemini analysis for one or more frames.

    Cache key is sha256 of the concatenated frame bytes in the given (stable)
    order PLUS the voice context, so re-sending the same album hits the cache
    only when the user comment is identical; a new voice note yields a fresh
    analysis. A single frame uses ``analyze_photo``; several frames use
    ``analyze_photos`` (one multimodal call). Result is cached unless it is an error.
    """
    h = hashlib.sha256()
    for data, _mime in frames:
        h.update(data)
    # Mix in the voice context so the same photo + a different comment is not
    # served a stale cached result. A length prefix avoids byte-boundary
    # collisions with the image bytes above.
    ctx_bytes = voice_context.encode("utf-8")
    h.update(b"|ctx|")
    h.update(str(len(ctx_bytes)).encode("ascii"))
    h.update(b"|")
    h.update(ctx_bytes)
    photo_hash = h.hexdigest()

    result = await get_cached_analysis(photo_hash)
    if result is not None:
        metrics.inc("photo_cache_total", {"result": "hit"})
        return result

    metrics.inc("photo_cache_total", {"result": "miss"})
    if len(frames) == 1:
        data, mime = frames[0]
        result = await gemini.analyze_photo(data, locale=locale, mime=mime, context=voice_context)
    else:
        result = await gemini.analyze_photos(frames, locale=locale, context=voice_context)
    if "error" not in result:
        await cache_analysis(photo_hash, result)
    return result


async def _analyze_and_reply(
    message: Message,
    bot: Bot,
    *,
    wait: Message,
    typing_task: asyncio.Task,
    frames: list[tuple[bytes, str]],
    locale: str,
    is_local: bool,
    is_prem: bool,
    used_bonus: bool,
    voice_context: str = "",
) -> None:
    """Shared post-download pipeline for photo, document and album audit paths.

    Runs cache lookup / Gemini analysis (single or multi-frame), before/after
    comparison, persistence, reminders, referral reward, and renders the
    free/premium response. ``wait`` is the "analyzing…" placeholder message and
    ``typing_task`` the typing indicator — both owned (cancelled/deleted) here.
    """
    user_id = message.from_user.id
    try:
        result = await _cached_analyze(frames, locale, voice_context)
    finally:
        typing_task.cancel()
        # Always remove the "analyzing…" placeholder, even if analysis raised,
        # so it never lingers forever. Swallow delete errors (msg already gone).
        try:
            await wait.delete()
        except Exception:
            logger.debug("could not delete 'analyzing' placeholder", exc_info=True)

    # Before/After comparison
    prev = await get_last_analysis(user_id)
    if prev:
        cmp_text = format_comparison(prev, result, locale)
        await message.answer(cmp_text, parse_mode="HTML")
    await save_last_analysis(user_id, result)

    # Save to report history and schedule follow-up reminder (fire-and-forget).
    # Supervised: a failure here (e.g. Odoo down) would otherwise lose the report
    # silently while the user's quota was already charged — log + metric instead.
    _supervise_task(
        asyncio.create_task(odoo.save_report(str(message.from_user.id), result)),
        name="save_report",
    )
    _supervise_task(
        asyncio.create_task(schedule_reminder(user_id, delay_days=30)),
        name="schedule_reminder",
    )

    # Referral first-scan reward (idempotent, fires once per new user)
    await ref_svc.reward_first_scan(user_id, bot)

    if not is_prem:
        if used_bonus:
            bonus_left = await ref_svc.get_bonus_scans(user_id)
            text = gemini.format_analysis_free(result, locale, settings.premium_price_stars)
            if bonus_left > 0:
                footer = (
                    f"\n\n<i>Использован бонусный анализ. Осталось бонусных: {bonus_left}</i>"
                    if locale == "ru"
                    else f"\n\n<i>Bonus scan used. Bonus analyses remaining: {bonus_left}</i>"
                )
                text += footer
            await message.answer(text, reply_markup=client_menu(locale, is_local))
        else:
            await premium_svc.increment_scan(user_id)
            remaining_after = await premium_svc.scans_remaining(user_id)
            text = gemini.format_analysis_free(result, locale, settings.premium_price_stars)
            if remaining_after > 0:
                footer = (
                    f"\n\n<i>Осталось бесплатных анализов сегодня: {remaining_after}</i>"
                    if locale == "ru"
                    else f"\n\n<i>Free analyses remaining today: {remaining_after}</i>"
                )
                text += footer
            await message.answer(text, reply_markup=client_menu(locale, is_local))
    else:
        text = gemini.format_analysis_premium(result, locale)
        await save_last_report(user_id, text)
        # Build keyboard: PDF + Voice + WebApp map + optional order button
        b = InlineKeyboardBuilder()
        pdf_label = "📄 Скачать PDF-отчёт" if locale == "ru" else "📄 Download PDF report"
        voice_label = "🎤 Голосовое заключение" if locale == "ru" else "🎤 Voice summary"
        b.row(
            InlineKeyboardButton(text=pdf_label, callback_data="report:pdf"),
            InlineKeyboardButton(text=voice_label, callback_data="report:voice"),
        )
        map_label = "🗺 Карта рисков" if locale == "ru" else "🗺 Risk map"
        webapp_data = gemini.analysis_to_webapp(result, scan_date=date.today().strftime("%d.%m.%Y"))
        webapp_key = await save_webapp_data(webapp_data)
        webapp_url = f"{settings.webapp_url}?k={webapp_key}"
        b.row(InlineKeyboardButton(text=map_label, web_app=WebAppInfo(url=webapp_url)))
        if is_local:
            b.row(
                InlineKeyboardButton(
                    text="🚗 Заказать профессиональный выезд"
                    if locale == "ru"
                    else "🚗 Order professional inspection",
                    callback_data="action:order",
                )
            )
        await message.answer(text, reply_markup=b.as_markup())


# ── Photo Audit (sent as uncompressed document) ────────────────────────────────


@router.message(AuditFlow.photo, F.document)
async def audit_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    """Accept thermal images sent as a *file* (full quality, no Telegram compression).

    Engineers send thermograms uncompressed to keep the temperature scale and
    detail intact. We accept only image MIME types, downscale oversized images,
    then route through the same analysis pipeline as compressed photos.
    """
    data = await state.get_data()
    locale: str = data.get("locale", "ru")
    is_local: bool = data.get("is_local", True)

    doc = message.document
    mime = (doc.mime_type or "").lower()

    if getattr(message, "media_group_id", None):
        # Album frame sent as an image-document. Skip non-image / oversized
        # frames silently; the rest of the album is still analyzed.
        if mime not in _SUPPORTED_DOC_MIME:
            return
        # Capacity gate BEFORE download: never pull bytes for frames we'd drop.
        if not _album_buffer.can_accept(message.media_group_id):
            return  # group already at max_frames; overflow flagged for flush notice
        if doc.file_size and doc.file_size > _MAX_PHOTO_BYTES:
            return
        file_io = await bot.download(doc)
        await _buffer_album_frame(message, state, bot, raw=file_io.read(), mime=mime)
        return

    if mime not in _SUPPORTED_DOC_MIME:
        # Not an image — keep the user in AuditFlow.photo so they can retry.
        err = (
            "⚠️ Это не изображение. Отправьте термоснимок картинкой "
            "(JPEG/PNG/WebP/HEIC) — фото или файлом-изображением."
            if locale == "ru"
            else "⚠️ That's not an image. Send a thermal photo as an image "
            "(JPEG/PNG/WebP/HEIC) — either a photo or an image file."
        )
        await message.answer(err)
        return

    user_id = message.from_user.id
    allowed, is_prem, used_bonus = await _check_quota(message, user_id, locale, is_local)
    if not allowed:
        # Keep AuditFlow.photo so the user can resend after upgrading.
        return
    await state.clear()

    metrics.inc("photo_input_total", {"kind": "document"})
    if doc.file_size and doc.file_size > _MAX_PHOTO_BYTES:
        err = (
            "⚠️ Файл слишком большой (максимум 20 МБ). Отправьте снимок меньшего размера."
            if locale == "ru"
            else "⚠️ File is too large (max 20 MB). Please send a smaller image."
        )
        await message.answer(err, reply_markup=client_menu(locale, is_local))
        return

    await bot.send_chat_action(message.chat.id, "upload_photo")
    wait = await message.answer(t("analyzing", locale))
    _typing = asyncio.create_task(typing_loop(bot, message.chat.id))
    try:
        file_io = await bot.download(doc)
        raw_bytes = file_io.read()
        # Downscale large/heavy images; hash is computed after preprocessing
        # inside the shared helper so cache keys match the analysed payload.
        prepared_bytes, prepared_mime = await image_prep.prepare_image_async(raw_bytes, mime)
    except Exception:
        _typing.cancel()
        await wait.delete()
        raise

    await _analyze_and_reply(
        message,
        bot,
        wait=wait,
        typing_task=_typing,
        frames=[(prepared_bytes, prepared_mime)],
        locale=locale,
        is_local=is_local,
        is_prem=is_prem,
        used_bonus=used_bonus,
        voice_context=data.get("voice_context", ""),
    )


# ── Voice context hint ────────────────────────────────────────────────────────


@router.message(AuditFlow.photo, F.voice)
async def audit_voice_hint(
    message: Message, state: FSMContext, bot: Bot, locale: str = "ru"
) -> None:
    """User can send a voice comment before the photo to add context to analysis."""
    wait = await message.answer(
        "🎤 Записываю комментарий..." if locale == "ru" else "🎤 Recording your note..."
    )
    file_io = await bot.download(message.voice)
    transcript = await gemini.transcribe_voice(file_io.read(), mime="audio/ogg")
    if transcript:
        await state.update_data(voice_context=transcript)
        note = transcript[:200]
        await wait.edit_text(
            f"✅ <b>Голосовой комментарий записан</b>\n"
            f"──────────────────────\n"
            f"<i>«{note}»</i>\n\n"
            f"📸 Теперь отправьте фото объекта."
            if locale == "ru"
            else f"✅ <b>Voice note recorded</b>\n"
            f"──────────────────────\n"
            f"<i>«{note}»</i>\n\n"
            f"📸 Now send the photo."
        )
    else:
        await wait.edit_text(
            "⚠️ Не удалось распознать голосовое. Отправьте фото."
            if locale == "ru"
            else "⚠️ Could not transcribe voice. Please send the photo."
        )


# ── Premium upgrade shortcut ──────────────────────────────────────────────────


@router.message(F.text.in_({BTN_UPGRADE, BTN_UPGRADE_EN}))
async def btn_upgrade(message: Message, locale: str = "ru", is_local: bool = True) -> None:
    from src.handlers.payments import cmd_premium

    await cmd_premium(message, locale=locale, is_local=is_local)


# ── Heat Loss Calculator ──────────────────────────────────────────────────────


@router.message(F.text.in_({BTN_CALC, BTN_CALC_EN}))
async def calc_start(
    message: Message, state: FSMContext, locale: str = "ru", is_local: bool = True
) -> None:
    await state.set_state(CalcFlow.area)
    await state.update_data(locale=locale, is_local=is_local)
    if locale == "ru":
        await message.answer(
            "📊 <b>Калькулятор теплопотерь</b>\n"
            "──────────────────────\n"
            "Шаг <b>1 из 3</b> — Площадь объекта\n\n"
            "Укажите общую площадь дома или квартиры в м².\n"
            "<i>Пример: 120</i>"
        )
    else:
        await message.answer(
            "📊 <b>Heat Loss Calculator</b>\n"
            "──────────────────────\n"
            "Step <b>1 of 3</b> — Object area\n\n"
            "Enter the total area of your home or apartment (m²).\n"
            "<i>Example: 120</i>"
        )


@router.message(CalcFlow.area, F.text)
async def calc_area(message: Message, state: FSMContext) -> None:
    try:
        area = float(message.text.replace(",", "."))
        if area <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число, например: <b>85</b>")
        return
    await state.update_data(area=area)
    await state.set_state(CalcFlow.heating)
    await message.answer("Шаг 2 из 3 — выберите тип отопления:", reply_markup=heating_kb())


@router.callback_query(CalcFlow.heating, F.data.startswith("heat:"))
async def calc_heating(call: CallbackQuery, state: FSMContext, locale: str = "ru") -> None:
    labels_ru = {"central": "Центральное", "gas": "Газ/Автономное", "electric": "Электрическое"}
    labels_en = {"central": "Central", "gas": "Gas/Autonomous", "electric": "Electric"}
    labels = labels_ru if locale == "ru" else labels_en
    key = call.data.split(":")[1]
    label = labels.get(key, key)
    await state.update_data(heating=label)
    await state.set_state(CalcFlow.payment)
    if locale == "ru":
        await call.message.edit_text(
            "📊 <b>Калькулятор теплопотерь</b>\n"
            "──────────────────────\n"
            f"✅ Шаг 2 из 3 — тип отопления: <b>{label}</b>\n\n"
            "Шаг <b>3 из 3</b> — Платёж за отопление\n\n"
            "Укажите сумму за самый холодный месяц (руб.).\n"
            "<i>Пример: 4 500</i>"
        )
    else:
        await call.message.edit_text(
            "📊 <b>Heat Loss Calculator</b>\n"
            "──────────────────────\n"
            f"✅ Step 2 of 3 — heating type: <b>{label}</b>\n\n"
            "Step <b>3 of 3</b> — Monthly heating bill\n\n"
            "Enter your bill for the coldest month (local currency).\n"
            "<i>Example: 4500</i>"
        )


@router.message(CalcFlow.payment, F.text)
async def calc_payment(message: Message, state: FSMContext) -> None:
    try:
        payment = float(message.text.replace(",", ".").replace(" ", ""))
        if payment <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите сумму в рублях, например: <b>3800</b>")
        return
    data = await state.get_data()
    locale: str = data.get("locale", "ru")
    await state.clear()
    wait = await message.answer(
        "⚙️ Считаю теплопотери..." if locale == "ru" else "⚙️ Calculating heat losses..."
    )

    from src.services.weather import get_weather_context

    weather_ctx = await get_weather_context()
    result = await gemini.calculate_losses(data["area"], data["heating"], payment, weather_ctx)
    await wait.delete()
    await message.answer(
        f"🧮 <b>Расчёт теплопотерь</b>\n{_SEP}\n\n{result}\n\n{_SEP}",
        reply_markup=order_kb(locale),
    )


# ── Lead Capture (local only) ─────────────────────────────────────────────────


@router.message(F.text == "🚗 Вызвать инженера")
async def lead_start(message: Message, state: FSMContext) -> None:
    await state.set_state(LeadFlow.contact)
    await message.answer(
        "🚗 <b>Вызов инженера на объект</b>\n"
        "──────────────────────\n"
        "Специалист приедет и выполнит полную\n"
        "тепловизионную диагностику здания.\n\n"
        "📱 Поделитесь номером телефона —\n"
        "перезвоним для уточнения деталей:",
        reply_markup=contact_kb(),
    )


@router.callback_query(F.data == "action:order")
async def lead_from_button(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LeadFlow.contact)
    await call.message.answer(
        "🚗 Отличный выбор! Поделитесь номером — инженер свяжется с вами в течение часа:",
        reply_markup=contact_kb(),
    )
    await call.answer()


@router.message(LeadFlow.contact, F.contact)
async def lead_contact(
    message: Message,
    state: FSMContext,
    bot: Bot,
    locale: str = "ru",
    is_local: bool = True,
) -> None:
    await state.clear()
    contact: Contact = message.contact
    phone = contact.phone_number
    name = f"{contact.first_name or ''} {contact.last_name or ''}".strip() or "Клиент"
    tg_ref = (
        f"@{message.from_user.username}"
        if message.from_user.username
        else f"tg://user?id={message.from_user.id}"
    )

    # Cache phone for geo detection refinement
    await roles.set_phone(message.from_user.id, phone)

    result = await odoo.create_lead(
        name=name,
        phone=phone,
        description=f"Заявка через Telegram-бот. TG: {tg_ref}",
    )
    odoo_status = (
        f"✅ Лид #{result} создан в Odoo" if result else "⚠️ Odoo недоступен — зафиксируй вручную"
    )
    for admin_id in settings.admin_ids:
        if admin_id:
            try:
                await bot.send_message(
                    admin_id,
                    f"📥 <b>Новая заявка на выезд!</b>\n"
                    f"──────────────────────\n"
                    f"👤 <b>Имя:</b> {name}\n"
                    f"📞 <b>Телефон:</b> <code>{phone}</code>\n"
                    f"🔗 <b>Telegram:</b> {tg_ref}\n"
                    f"──────────────────────\n"
                    f"🗄 {odoo_status}",
                )
            except Exception:
                pass

    await message.answer(
        "✅ <b>Заявка на выезд принята!</b>\n"
        "──────────────────────\n"
        "🚗 Инженер свяжется с вами для согласования времени.\n\n"
        "<i>Среднее время ответа — 15 минут в рабочие часы.</i>",
        reply_markup=client_menu(locale, is_local),
    )


# ── PDF Report download ───────────────────────────────────────────────────────


@router.callback_query(F.data == "report:pdf")
async def download_pdf(call: CallbackQuery, locale: str = "ru") -> None:
    user_id = call.from_user.id
    report_text = await get_last_report(user_id)

    if not report_text:
        msg = (
            "⚠️ Отчёт не найден — анализ устарел (хранится 24 ч). Сделайте новый анализ."
            if locale == "ru"
            else "⚠️ Report not found — it expired (stored for 24 h). Run a new analysis."
        )
        await call.answer(msg, show_alert=True)
        return

    await call.answer("⏳ Генерирую PDF..." if locale == "ru" else "⏳ Generating PDF...")

    from datetime import datetime

    from src.services.pdf import generate_report

    last_analysis = await get_last_analysis(user_id)
    pdf_bytes = generate_report(report_text, locale, analysis=last_analysis)
    date_str = datetime.now(UTC).strftime("%Y%m%d_%H%M")
    filename = f"InfraScan_{date_str}.pdf"

    caption = (
        "📄 <b>PDF-отчёт готов!</b>\n"
        "──────────────────────\n"
        "<i>Документ содержит полный результат ИИ-анализа,\n"
        "уровень риска и рекомендации по устранению.</i>"
        if locale == "ru"
        else "📄 <b>PDF report ready!</b>\n"
        "──────────────────────\n"
        "<i>The document contains the full AI analysis,\n"
        "risk level and remediation recommendations.</i>"
    )
    await call.message.answer_document(
        document=BufferedInputFile(pdf_bytes, filename=filename),
        caption=caption,
    )


# ── Voice Report ──────────────────────────────────────────────────────────────


@router.callback_query(F.data == "report:voice")
async def download_voice(call: CallbackQuery, locale: str = "ru") -> None:
    user_id = call.from_user.id
    report_text = await get_last_report(user_id)

    if not report_text:
        msg = (
            "⚠️ Отчёт не найден — анализ устарел (хранится 24 ч). Сделайте новый анализ."
            if locale == "ru"
            else "⚠️ Report not found — it expired (stored for 24 h). Run a new analysis."
        )
        await call.answer(msg, show_alert=True)
        return

    await call.answer(
        "⏳ Генерирую голосовое заключение..."
        if locale == "ru"
        else "⏳ Generating voice summary..."
    )

    from src.services.tts import generate_voice

    mp3_bytes = await generate_voice(report_text, locale)
    await call.message.answer_voice(
        voice=BufferedInputFile(mp3_bytes, filename="InfraScan_report.mp3"),
        caption=(
            "🎤 <b>Голосовое заключение готово</b>"
            if locale == "ru"
            else "🎤 <b>Voice summary ready</b>"
        ),
    )
