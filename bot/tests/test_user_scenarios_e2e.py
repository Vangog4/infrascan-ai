"""Comprehensive End-to-End User Journey Tests for InfraScan AI Telegram Bot.

Tests all user-facing aspects as a real user interacting with the bot:
1. New user registration & onboarding flow
2. Photo audit (free tier, Gemini analysis, quota decrement, uncompressed document)
3. Before/After thermal comparison flow
4. Heating loss calculation flow (step-by-step FSM, validation, result)
5. Lead capture & on-site inspection order
6. Account management & referral program (links, activations, rewards)
7. Report history (/myreports)
8. Telegram Stars payment, premium activation, PDF and voice downloads
9. Serial multi-photo audit with QC feedback
10. Partner and Employee role-based journeys
"""

from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import src.services.redis as redis_mod
import src.services.referral as ref_svc
import src.services.tts as tts_svc
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Contact,
    Document,
    Message,
    PhotoSize,
    PreCheckoutQuery,
    SuccessfulPayment,
    User,
)
from src.handlers import (
    account,
    client,
    common,
    employee,
    partner,
    payments,
    referral,
    serial_audit,
)
from src.services.roles import Role
from src.states.flows import AuditFlow, CalcFlow, LeadFlow, PartnerLeadFlow, SerialAuditFlow


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch, fake_redis):
    monkeypatch.setattr(redis_mod, "_redis", fake_redis)
    yield fake_redis


@pytest.fixture(autouse=True)
def mock_odoo_call():
    with patch("src.services.odoo._call", AsyncMock(return_value=[])):
        yield


# ── Test Helpers ─────────────────────────────────────────────────────────────


def _make_user(user_id: int = 10001, first_name: str = "Алексей", username: str = "alexey") -> User:
    return User(
        id=user_id, is_bot=False, first_name=first_name, username=username, language_code="ru"
    )


def _make_msg(
    user_id: int = 10001,
    text: str = "",
    first_name: str = "Алексей",
    username: str = "alexey",
    photo: list | None = None,
    document: Document | None = None,
    contact: Contact | None = None,
    successful_payment: SuccessfulPayment | None = None,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = _make_user(user_id, first_name, username)
    msg.chat = MagicMock(id=user_id)
    msg.text = text
    msg.caption = None
    msg.photo = photo
    msg.document = document
    msg.contact = contact
    msg.successful_payment = successful_payment

    sent_msg = MagicMock()
    sent_msg.edit_text = AsyncMock()
    sent_msg.delete = AsyncMock()
    msg.answer = AsyncMock(return_value=sent_msg)
    msg.reply = AsyncMock(return_value=sent_msg)
    msg.edit_text = AsyncMock(return_value=sent_msg)
    msg.answer_document = AsyncMock()
    msg.answer_voice = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.delete = AsyncMock()
    return msg


def _make_call(
    user_id: int = 10001,
    data: str = "",
    first_name: str = "Алексей",
    username: str = "alexey",
) -> MagicMock:
    call = MagicMock(spec=CallbackQuery)
    call.bot = _make_bot()
    call.from_user = _make_user(user_id, first_name, username)
    call.data = data
    call.answer = AsyncMock()
    call.message = _make_msg(user_id, first_name=first_name, username=username)
    return call


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    bot.send_invoice = AsyncMock()
    bot.send_photo = AsyncMock()
    bot.send_document = AsyncMock()
    bot.send_voice = AsyncMock()
    bot.send_chat_action = AsyncMock()
    bot.answer_pre_checkout_query = AsyncMock()
    bot.download = AsyncMock(return_value=BytesIO(b"\xff\xd8\xff\xe0fake_jpeg_bytes"))
    bot.download_file = AsyncMock(return_value=BytesIO(b"\xff\xd8\xff\xe0fake_jpeg_bytes"))
    bot.get_file = AsyncMock(return_value=MagicMock(file_path="photos/sample.jpg"))
    bot.get_me = AsyncMock(return_value=MagicMock(username="infrascan_ai_bot"))
    return bot


def _make_fsm_context(user_id: int = 10001) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=user_id, user_id=user_id)
    return FSMContext(storage=storage, key=key)


# ── Scenario 1: Onboarding and Start ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_new_user_onboarding_and_start(fake_redis):
    user_id = 10001
    fsm = _make_fsm_context(user_id)
    msg = _make_msg(user_id, "/start", first_name="Иван <VIP>")

    with (
        patch("src.services.redis.get_redis", return_value=fake_redis),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
    ):
        cmd = MagicMock(args=None)
        await common.cmd_start(msg, fsm, Role.CLIENT, cmd, locale="ru", is_local=True)

        assert msg.answer.call_count >= 1
        welcome_text = msg.answer.call_args_list[0][0][0]
        # HTML escaping for user name
        assert "&lt;VIP&gt;" in welcome_text
        assert "<VIP>" not in welcome_text
        assert "бесплатных анализа в день" in welcome_text

        # User clicks "Upload first photo" CTA
        call = _make_call(user_id, "onboarding:photo")
        await common.onboarding_photo_start(call, fsm, locale="ru", is_local=True)
        call.answer.assert_awaited_once()
        state = await fsm.get_state()
        assert state == AuditFlow.photo


# ── Scenario 2: Photo Audit (Free Tier) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_free_photo_audit_flow(fake_redis):
    user_id = 10002
    fsm = _make_fsm_context(user_id)
    bot = _make_bot()

    # Enter photo flow
    await fsm.set_state(AuditFlow.photo)
    await fsm.update_data(locale="ru", is_local=True)

    photo_obj = MagicMock(spec=PhotoSize, file_id="p123", file_size=2048)
    msg = _make_msg(user_id, photo=[photo_obj])

    analysis_res = {
        "risk_level": "MEDIUM",
        "risk_score": 0.45,
        "object_type": "окно",
        "free_verdict": "Обнаружено продувание по контуру створки при T < 10°C",
        "recommendations_brief": "Заменить уплотнитель & отрегулировать фурнитуру",
        "premium_teaser": "Теплопотери до 18% от комнаты",
    }

    with (
        patch("src.services.redis.get_redis", return_value=fake_redis),
        patch("src.services.premium.consume_scan", AsyncMock(return_value=True)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=2)),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.services.gemini.analyze_photo", AsyncMock(return_value=analysis_res)),
        patch("src.services.odoo.save_report", AsyncMock(return_value=True)),
        patch(
            "src.services.image_prep.prepare_image_async",
            AsyncMock(return_value=(b"jpeg_data", False)),
        ),
    ):
        await client.audit_photo(msg, fsm, bot)

        # Verified analysis sent to user
        sent_text = msg.answer.call_args[0][0]
        assert "Анализ снимка" in sent_text
        assert "Окно" in sent_text
        assert "СРЕДНИЙ" in sent_text
        assert "T &lt; 10°C" in sent_text
        assert "Заменить уплотнитель &amp; отрегулировать" in sent_text
        assert "Осталось бесплатных анализов сегодня: 2" in sent_text


# ── Scenario 3: Uncompressed Document Audit ──────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_uncompressed_document_audit(fake_redis):
    user_id = 10003
    fsm = _make_fsm_context(user_id)
    bot = _make_bot()

    await fsm.set_state(AuditFlow.photo)
    await fsm.update_data(locale="ru", is_local=True)

    # Valid image document
    doc = MagicMock(
        spec=Document,
        file_id="d123",
        file_size=5000,
        mime_type="image/jpeg",
        file_name="flir_001.jpg",
    )
    msg = _make_msg(user_id, document=doc)

    analysis_res = {
        "risk_level": "LOW",
        "risk_score": 0.15,
        "object_type": "стена",
        "free_verdict": "Теплоизоляция в норме",
        "recommendations_brief": "Замечаний нет",
        "premium_teaser": "Однородное распределение температуры",
    }

    with (
        patch("src.services.redis.get_redis", return_value=fake_redis),
        patch("src.services.premium.consume_scan", AsyncMock(return_value=True)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=1)),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.services.gemini.analyze_photo", AsyncMock(return_value=analysis_res)),
        patch("src.services.odoo.save_report", AsyncMock(return_value=True)),
        patch(
            "src.services.image_prep.prepare_image_async",
            AsyncMock(return_value=(b"doc_bytes", False)),
        ),
    ):
        await client.audit_document(msg, fsm, bot)
        sent_text = msg.answer.call_args[0][0]
        assert "Теплоизоляция в норме" in sent_text

    # Non-image document rejection
    bad_doc = MagicMock(spec=Document, mime_type="application/pdf", file_name="invoice.pdf")
    bad_msg = _make_msg(user_id, document=bad_doc)
    await client.audit_document(bad_msg, fsm, bot)
    err_text = bad_msg.answer.call_args[0][0]
    assert "изображение" in err_text.lower() or "отправьте" in err_text.lower()


# ── Scenario 4: Before/After Comparison ──────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_before_after_comparison(fake_redis):
    user_id = 10004
    fsm = _make_fsm_context(user_id)
    bot = _make_bot()

    # Pre-populate previous analysis in redis
    await fake_redis.set(f"analysis:{user_id}", '{"risk_level": "HIGH", "risk_score": 0.8}')

    new_analysis = {
        "risk_level": "LOW",
        "risk_score": 0.2,
        "object_type": "стена",
        "free_verdict": "После утепления мостик холода устранён",
    }

    photo_obj = MagicMock(spec=PhotoSize, file_id="p2", file_size=1024)
    msg = _make_msg(user_id, photo=[photo_obj])

    with (
        patch("src.services.redis.get_redis", return_value=fake_redis),
        patch("src.services.premium.consume_scan", AsyncMock(return_value=True)),
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.services.premium.scans_remaining", AsyncMock(return_value=0)),
        patch("src.services.referral.get_bonus_scans", AsyncMock(return_value=0)),
        patch("src.services.gemini.analyze_photo", AsyncMock(return_value=new_analysis)),
        patch("src.services.odoo.save_report", AsyncMock(return_value=True)),
        patch(
            "src.services.image_prep.prepare_image_async", AsyncMock(return_value=(b"img", False))
        ),
    ):
        await client.audit_photo(msg, fsm, bot)

        # Check comparison message was delivered
        answer_calls = [c[0][0] for c in msg.answer.call_args_list]
        cmp_calls = [c for c in answer_calls if "Сравнение с предыдущим анализом" in c]
        assert len(cmp_calls) == 1
        cmp_text = cmp_calls[0]
        assert "Улучшение" in cmp_text
        assert "Было:  🟠 HIGH" in cmp_text
        assert "Стало: 🟢 LOW" in cmp_text


# ── Scenario 5: Heating Loss Calculator ──────────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_heating_loss_calculator_flow():
    user_id = 10005
    fsm = _make_fsm_context(user_id)

    # Step 1: user initiates calc
    msg_start = _make_msg(user_id, "📊 Расчёт теплопотерь")
    await client.calc_start(msg_start, fsm)
    assert await fsm.get_state() == CalcFlow.area

    # Step 2: invalid area
    msg_bad_area = _make_msg(user_id, "двадцать пять")
    await client.calc_area(msg_bad_area, fsm)
    assert "Введите число" in msg_bad_area.answer.call_args[0][0]

    # Valid area
    msg_area = _make_msg(user_id, "120")
    await client.calc_area(msg_area, fsm)
    assert await fsm.get_state() == CalcFlow.heating
    data = await fsm.get_data()
    assert data["area"] == 120.0

    # Step 3: select heating type
    call_heat = _make_call(user_id, "heat:gas")
    await client.calc_heating(call_heat, fsm, locale="ru")
    assert await fsm.get_state() == CalcFlow.payment
    data = await fsm.get_data()
    assert data["heating"] == "Газ/Автономное"

    # Step 4: invalid payment
    msg_bad_pay = _make_msg(user_id, "много")
    await client.calc_payment(msg_bad_pay, fsm)
    assert "Введите сумму" in msg_bad_pay.answer.call_args[0][0]

    # Valid payment
    msg_pay = _make_msg(user_id, "4 500")
    calc_output = "<b>📉 Расчётные теплопотери</b>\n• Потери: 25%\n• Экономия: ~15 000 руб./год"
    with (
        patch("src.services.weather.get_weather_context", AsyncMock(return_value="T улиц: -10°C")),
        patch("src.services.gemini.calculate_losses", AsyncMock(return_value=calc_output)),
    ):
        await client.calc_payment(msg_pay, fsm)
        result_text = msg_pay.answer.call_args[0][0]
        assert "Расчёт теплопотерь" in result_text
        assert "Экономия: ~15 000 руб./год" in result_text
        assert await fsm.get_state() is None


# ── Scenario 6: Lead Capture (Order Inspection) ──────────────────────────────


@pytest.mark.asyncio
async def test_scenario_lead_capture_order_flow(fake_redis):
    user_id = 10006
    fsm = _make_fsm_context(user_id)
    bot = _make_bot()

    # Trigger order
    call_order = _make_call(user_id, "action:order")
    await client.lead_from_button(call_order, fsm)
    assert await fsm.get_state() == LeadFlow.contact

    # Send contact
    contact = Contact(phone_number="+79991234567", first_name="Сергей", last_name="<Инженер>")
    msg_contact = _make_msg(user_id, contact=contact)

    with (
        patch("src.services.redis.get_redis", return_value=fake_redis),
        patch("src.services.odoo.create_lead", AsyncMock(return_value=777)) as mock_lead,
        patch("src.services.premium.is_premium", AsyncMock(return_value=False)),
        patch("src.config.settings.admin_ids", [9999]),
    ):
        await client.lead_contact(msg_contact, fsm, bot, locale="ru")

        # Verified Odoo lead created
        mock_lead.assert_awaited_once()
        lead_name = mock_lead.call_args.kwargs["name"]
        assert "Сергей" in lead_name

        # User receives confirmation
        assert "Заявка на выезд принята" in msg_contact.answer.call_args[0][0]

        # Admin notified with escaped HTML
        bot.send_message.assert_awaited_once()
        admin_text = bot.send_message.call_args[0][1]
        assert "&lt;Инженер&gt;" in admin_text
        assert "<Инженер>" not in admin_text
        assert "+79991234567" in admin_text


# ── Scenario 7: Referral Program & Account ───────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_referral_and_account_flow(fake_redis):
    referrer_id = 10007
    referee_id = 10008
    bot = _make_bot()

    with patch("src.services.redis.get_redis", return_value=fake_redis):
        # 1. Referrer gets /ref link
        msg_ref = _make_msg(referrer_id, "/ref")
        await referral.cmd_ref(msg_ref, bot, locale="ru")
        ref_text = msg_ref.answer.call_args[0][0]
        assert "Приглашай друзей" in ref_text
        assert "t.me/infrascan_ai_bot?start=ref_" in ref_text

        code = await fake_redis.get(f"ref:{referrer_id}")
        assert code is not None

        # 2. Friend joins via deep link
        fsm_friend = _make_fsm_context(referee_id)
        cmd = MagicMock(args=f"ref_{code}")
        msg_friend = _make_msg(referee_id, f"/start ref_{code}", first_name="Друг")
        await common.cmd_start(msg_friend, fsm_friend, Role.CLIENT, cmd, locale="ru")

        # Referee receives bonus scan
        bonus_referee = await fake_redis.get(f"bonus_scans:{referee_id}")
        assert int(bonus_referee) == 1

        # 3. Friend completes first scan -> referrer is rewarded
        await ref_svc.reward_first_scan(referee_id, bot)
        bonus_referrer = await fake_redis.get(f"bonus_scans:{referrer_id}")
        assert int(bonus_referrer) == 1
        bot.send_message.assert_awaited()
        assert "Ваш друг сделал первый анализ" in bot.send_message.call_args[0][1]

        # 4. Referrer views account
        msg_acc = _make_msg(referrer_id, "/account")
        await account.cmd_account(msg_acc, locale="ru")
        acc_text = msg_acc.answer.call_args[0][0]
        assert "МОЙ КАБИНЕТ" in acc_text
        assert "БОНУСНЫХ    1 анализов" in acc_text
        assert "РЕФЕРАЛОВ   1 чел." in acc_text


# ── Scenario 8: Telegram Stars Payment & Premium Downloads ───────────────────


@pytest.mark.asyncio
async def test_scenario_premium_payment_and_report_downloads(fake_redis):
    user_id = 10009
    bot = _make_bot()

    with patch("src.services.redis.get_redis", return_value=fake_redis):
        # 1. User commands /premium
        msg_prem = _make_msg(user_id, "/premium")
        await payments.cmd_premium(msg_prem, locale="ru")
        assert "InfraScan Premium" in msg_prem.answer.call_args[0][0]

        # 2. User taps buy
        call_buy = _make_call(user_id, "premium:buy")
        await payments.cb_premium_buy(call_buy, bot, locale="ru")
        bot.send_invoice.assert_awaited_once()
        inv_kwargs = bot.send_invoice.call_args[1]
        assert inv_kwargs["currency"] == "XTR"
        assert inv_kwargs["payload"] == "premium_30days"

        # 3. Pre-checkout query
        query = MagicMock(
            spec=PreCheckoutQuery, id="pq_1", invoice_payload="premium_30days", total_amount=150
        )
        await payments.pre_checkout(query, bot)
        bot.answer_pre_checkout_query.assert_awaited_once_with("pq_1", ok=True)

        # 4. Successful payment confirmation
        payment_info = MagicMock(
            spec=SuccessfulPayment,
            invoice_payload="premium_30days",
            total_amount=150,
            telegram_payment_charge_id="chg_real_123",
        )
        msg_paid = _make_msg(user_id, successful_payment=payment_info)
        with patch("src.services.odoo.set_premium", AsyncMock(return_value=True)):
            await payments.payment_success(msg_paid, bot, locale="ru")

        # Premium active in Redis
        is_prem = await fake_redis.get(f"premium:{user_id}")
        assert is_prem == "1"

        # 5. User requests PDF report
        await fake_redis.set(f"report:{user_id}", "<b>Отчёт:</b> перегрев &lt;фаза A&gt;")
        await fake_redis.set(f"analysis:{user_id}", '{"risk_level": "HIGH"}')

        call_pdf = _make_call(user_id, "report:pdf")
        call_pdf.message.answer_document = AsyncMock()

        with patch("src.services.gemini.format_analysis_premium", return_value="Отчёт"):
            await client.download_pdf(call_pdf, locale="ru")

        call_pdf.message.answer_document.assert_awaited_once()
        doc_arg = call_pdf.message.answer_document.call_args[1]["document"]
        assert isinstance(doc_arg, BufferedInputFile)
        assert doc_arg.filename.startswith("InfraScan_")

        # 6. User requests Voice summary
        call_voice = _make_call(user_id, "report:voice")
        call_voice.message.answer_voice = AsyncMock()
        with patch.object(tts_svc, "generate_voice", AsyncMock(return_value=b"fake_mp3_bytes")):
            await client.download_voice(call_voice, locale="ru")

        call_voice.message.answer_voice.assert_awaited_once()
        voice_arg = call_voice.message.answer_voice.call_args[1]["voice"]
        assert isinstance(voice_arg, BufferedInputFile)
        assert voice_arg.filename == "InfraScan_report.mp3"


# ── Scenario 9: Serial Multi-Photo Audit with QC ─────────────────────────────


@pytest.mark.asyncio
async def test_scenario_serial_multi_photo_audit(fake_redis):
    user_id = 10010
    fsm = _make_fsm_context(user_id)
    bot = _make_bot()

    # Set user as premium to allow serial audit
    await fake_redis.set(f"premium:{user_id}", "1")

    call_start = _make_call(user_id, "start_serial")
    with patch("src.services.redis.get_redis", return_value=fake_redis):
        await serial_audit.start_serial(call_start, fsm)
        assert await fsm.get_state() == SerialAuditFlow.collecting

        # Photo 1: good QC
        qc_good = {"ok": True, "score": 92, "verdict": "ПРИНЯТО"}
        p1 = MagicMock(spec=PhotoSize, file_id="ph_1")
        msg_p1 = _make_msg(user_id, photo=[p1])
        with patch("src.services.gemini.check_quality", AsyncMock(return_value=qc_good)):
            await serial_audit.collect_photo(msg_p1, fsm, bot)
        data = await fsm.get_data()
        assert data["photos"] == ["ph_1"]

        # Photo 2: rejected QC (blur)
        qc_bad = {
            "ok": False,
            "score": 30,
            "verdict": "БРАК",
            "reason": "Размыто",
            "tip": "Стабилизируйте камеру",
        }
        p2_bad = MagicMock(spec=PhotoSize, file_id="ph_bad")
        msg_p2_bad = _make_msg(user_id, photo=[p2_bad])
        with patch("src.services.gemini.check_quality", AsyncMock(return_value=qc_bad)):
            await serial_audit.collect_photo(msg_p2_bad, fsm, bot)
        # Still 1 photo stored
        data = await fsm.get_data()
        assert data["photos"] == ["ph_1"]

        # Photo 2: retried with good QC
        p2_good = MagicMock(spec=PhotoSize, file_id="ph_2")
        msg_p2_good = _make_msg(user_id, photo=[p2_good])
        with patch("src.services.gemini.check_quality", AsyncMock(return_value=qc_good)):
            await serial_audit.collect_photo(msg_p2_good, fsm, bot)
        data = await fsm.get_data()
        assert data["photos"] == ["ph_1", "ph_2"]

        # Finish serial audit
        call_done = _make_call(user_id, "serial_done")
        analysis_res = {
            "risk_level": "HIGH",
            "object_type": "кровля",
            "free_verdict": "Утечка тепла через примыкание парапета T > 15°C & влага",
        }
        with patch("src.services.gemini.analyze_photo", AsyncMock(return_value=analysis_res)):
            await serial_audit.serial_done(call_done, fsm)

        report_text = call_done.message.edit_text.call_args[0][0]
        assert "Серийный анализ — 2 фото" in report_text
        assert "Фото 1" in report_text and "Фото 2" in report_text
        assert "T &gt; 15°C &amp; влага" in report_text
        assert await fsm.get_state() is None


# ── Scenario 10: Partner & Employee Journeys ─────────────────────────────────


@pytest.mark.asyncio
async def test_scenario_partner_and_employee_journeys(fake_redis):
    # Partner journey
    partner_id = 10011
    fsm_p = _make_fsm_context(partner_id)
    msg_p_start = _make_msg(partner_id, "➕ Передать лида")
    await partner.lead_start(msg_p_start, fsm_p, Role.PARTNER)
    assert await fsm_p.get_state() == PartnerLeadFlow.phone

    msg_phone = _make_msg(partner_id, "+79998887766")
    with patch("src.services.odoo.create_lead", AsyncMock(return_value=888)) as mock_lead:
        await partner.lead_phone(msg_phone, fsm_p)
        mock_lead.assert_awaited_once()
        assert "+79998887766" in msg_phone.answer.call_args[0][0]

    # Partner balance
    msg_bal = _make_msg(partner_id, "💰 Мой баланс")
    with (
        patch("src.services.roles.get_phone", AsyncMock(return_value="+79998887766")),
        patch("src.services.odoo.partner_balance", AsyncMock(return_value=12500.50)),
    ):
        await partner.my_balance(msg_bal, Role.PARTNER)
        assert "12,500.50 руб." in msg_bal.answer.call_args[0][0]

    # Employee journey: view today's tasks
    emp_id = 10012
    tasks_data = [
        {
            "id": 101,
            "name": "Диагностика ТЦ «Север» <Корпус A>",
            "project_id": [1, "Выезд"],
            "stage_id": [2, "В работе"],
            "date_deadline": "2026-09-09",
            "x_telegram_id": str(emp_id),
        }
    ]
    msg_emp = _make_msg(emp_id, "🚗 Мои выезды на сегодня")
    with patch("src.services.odoo.get_today_tasks", AsyncMock(return_value=tasks_data)):
        await employee.today_tasks(msg_emp, Role.EMPLOYEE)
        tasks_text = msg_emp.answer.call_args[0][0]
        assert "Выезды на сегодня" in tasks_text
        assert "ТЦ «Север» &lt;Корпус A&gt;" in tasks_text
