"""
Gemini Vision service.

analyze_photo() returns a raw dict (JSON from Gemini).
Use format_analysis_free() / format_analysis_premium() to render for Telegram.
"""

import asyncio
import json
import logging
import random
import re
import time

from google import genai
from google.genai import types

from src.config import settings
from src.services import metrics

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


# ── Retry / fallback helper ────────────────────────────────────────────────────

_MAX_ATTEMPTS = 3  # attempts on the primary model
_BACKOFF_BASE = 1.0  # seconds: 1s, 2s, 4s ...
_TRANSIENT_CODES = {429, 500, 502, 503, 504}
_TRANSIENT_STATUSES = {"UNAVAILABLE", "RESOURCE_EXHAUSTED", "INTERNAL", "DEADLINE_EXCEEDED"}
_TRANSIENT_TYPES = (asyncio.TimeoutError, TimeoutError, ConnectionError)


def _is_transient(exc: Exception) -> bool:
    """Best-effort detection of retryable (transient) Gemini/network errors.

    Checks, in order: known network/timeout exception types, numeric ``code``
    and string ``status`` attributes (as exposed by google-genai APIError), and
    finally the string representation as a last resort.
    """
    if isinstance(exc, _TRANSIENT_TYPES):
        return True

    code = getattr(exc, "code", None)
    try:
        if code is not None and int(code) in _TRANSIENT_CODES:
            return True
    except (TypeError, ValueError):
        pass

    status = getattr(exc, "status", None)
    if isinstance(status, str) and status.upper() in _TRANSIENT_STATUSES:
        return True

    text = str(exc).upper()
    if any(s in text for s in _TRANSIENT_STATUSES):
        return True
    if any(f" {c}" in text or f"{c} " in text or f"[{c}]" in text for c in _TRANSIENT_CODES):
        return True
    return False


async def _generate_with_retry(*, model: str, contents, config=None):
    """Call ``generate_content`` with retries on transient errors + optional fallback.

    - Up to ``_MAX_ATTEMPTS`` attempts on ``model`` with exponential backoff + jitter,
      retrying ONLY on transient errors (503/429/5xx, UNAVAILABLE/RESOURCE_EXHAUSTED,
      timeouts/network). Non-transient errors (4xx except 429, JSONDecode, etc.) are
      raised immediately.
    - After the primary model is exhausted, if ``settings.gemini_fallback_model`` is
      set, one attempt is made on the fallback model. Otherwise the last error is raised.
    """
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            t0 = time.monotonic()
            resp = await _get().aio.models.generate_content(
                model=model, contents=contents, config=config
            )
            metrics.observe(
                "gemini_request_duration_seconds", time.monotonic() - t0, {"model": model}
            )
            # outcome=ok on first attempt, outcome=retry if it took a retry to succeed
            outcome = "ok" if attempt == 1 else "retry"
            metrics.inc("gemini_requests_total", {"model": model, "outcome": outcome})
            return resp
        except Exception as e:
            if not _is_transient(e):
                metrics.inc("gemini_requests_total", {"model": model, "outcome": "error"})
                raise
            last_exc = e
            if attempt < _MAX_ATTEMPTS:
                metrics.inc("gemini_retries_total", {"model": model})
                delay = _BACKOFF_BASE * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                logger.warning(
                    "Gemini transient error on %s (attempt %d/%d): %s — retrying in %.2fs",
                    model,
                    attempt,
                    _MAX_ATTEMPTS,
                    e,
                    delay,
                )
                await asyncio.sleep(delay)

    fallback = settings.gemini_fallback_model
    if fallback:
        logger.warning(
            "Gemini primary model %s exhausted after %d attempts, trying fallback %s",
            model,
            _MAX_ATTEMPTS,
            fallback,
        )
        try:
            t0 = time.monotonic()
            resp = await _get().aio.models.generate_content(
                model=fallback, contents=contents, config=config
            )
            metrics.observe(
                "gemini_request_duration_seconds", time.monotonic() - t0, {"model": fallback}
            )
            metrics.inc("gemini_requests_total", {"model": fallback, "outcome": "fallback"})
            return resp
        except Exception:
            metrics.inc("gemini_requests_total", {"model": fallback, "outcome": "error"})
            raise

    logger.error(
        "Gemini model %s failed after %d attempts, no fallback configured: %s",
        model,
        _MAX_ATTEMPTS,
        last_exc,
    )
    metrics.inc("gemini_requests_total", {"model": model, "outcome": "error"})
    assert last_exc is not None
    raise last_exc


# ── Stubs (GEMINI_STUB=true) ──────────────────────────────────────────────────

_STUB_ANALYSIS = {
    "object_type": "wall",
    "risk_level": "MEDIUM",
    "risk_score": 0.58,
    "temperature_observations": [
        "Перепад температур в зоне откоса: +4°C относительно основной плоскости",
        "Равномерный фон стены 18–19°C, аномалия в верхнем левом углу",
    ],
    "problems": [
        {
            "type": "thermal_bridge",
            "location": "верхний левый угол",
            "severity": "medium",
            "description": "Мостик холода в узле примыкания стены к перекрытию",
        },
        {
            "type": "moisture",
            "location": "откос окна",
            "severity": "low",
            "description": "Следы капиллярного увлажнения, характерные для нарушения герметизации",
        },
    ],
    "free_verdict": (
        "На снимке — наружная стена с признаками мостика холода в зоне перекрытия. "
        "Уровень риска СРЕДНИЙ: дефект не критичен, но при отсутствии мер приведёт "
        "к образованию конденсата и плесени в течение 1–2 сезонов."
    ),
    "premium_analysis": (
        "Тепловизионная картина указывает на разрыв теплового контура в узле «стена–плита». "
        "Корневая причина — недостаточное утепление торца плиты перекрытия при строительстве. "
        "При температуре наружного воздуха ниже −10°C точка росы смещается внутрь стены, "
        "что создаёт условия для роста плесени и постепенного разрушения штукатурного слоя. "
        "Вторичный риск: намокание минераловатного утеплителя снижает его R-значение на 30–50%."
    ),
    "recommendations_brief": "Утеплить торец плиты перекрытия с устройством «тёплого» откоса.",
    "recommendations_detailed": [
        "Шаг 1: вскрыть откос, проверить герметизацию монтажной пеной",
        "Шаг 2: нанести PIR-плиту 30 мм на торец плиты перекрытия",
        "Шаг 3: оштукатурить по стеклосетке, восстановить пароизоляционную плёнку",
        "Материалы: PIR 30 мм (λ=0.022), дюбели-грибки 8×120, штукатурка Ceresit CT 85",
    ],
    "premium_teaser": "Выявлен ещё один скрытый дефект в зоне радиатора — возможна протечка.",
    "_stub": True,
}

_STUB_QC = {
    "ok": True,
    "score": 82,
    "verdict": "ПРИНЯТО",
    "reason": None,
    "tip": None,
    "object": "наружная стена, откос окна",
    "_stub": True,
}

_STUB_LOSSES = (
    "━━━━━━━━━━━━━━━━━━━━━\n\n"
    "<b>📉 Расчётные теплопотери</b>\n"
    "• Скрытые потери: <b>18–24%</b> от общего потребления\n"
    "• Ежемесячные потери: ~<b>1 800 руб.</b> в холодный период\n"
    "• Потери в год: ~<b>7 200 руб.</b>\n\n"
    "<b>💰 Окупаемость диагностики</b>\n"
    "• Стоимость обследования: от <b>4 000 руб.</b>\n"
    "• Срок окупаемости: <b>7 месяцев</b>\n"
    "• Потенциальная экономия: ~<b>7 200 руб./год</b> после устранения утечек\n\n"
    "<b>📊 Вывод</b>\n"
    "Диагностика окупится уже в первый отопительный сезон — закажите выезд специалиста сейчас.\n\n"
    "━━━━━━━━━━━━━━━━━━━━━"
)


# ── Constants ────────────────────────────────────────────────────────────────

_SEP = "━━━━━━━━━━━━━━━━━━━━━"

_RISK_EMOJI = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "💀"}
_SEV_EMOJI = {"low": "🟡", "medium": "🟠", "high": "🔴", "critical": "💀"}

_RISK_LABEL = {
    "ru": {"LOW": "НИЗКИЙ", "MEDIUM": "СРЕДНИЙ", "HIGH": "ВЫСОКИЙ", "CRITICAL": "КРИТИЧЕСКИЙ"},
    "en": {"LOW": "LOW", "MEDIUM": "MEDIUM", "HIGH": "HIGH", "CRITICAL": "CRITICAL"},
}
_OBJECT_LABEL = {
    "ru": {
        "window": "Окно / проём",
        "wall": "Стена / перекрытие",
        "roof": "Кровля",
        "electrical": "Электрощит / проводка",
        "facade": "Фасад / наружная стена",
        "floor": "Пол / стяжка",
        "other": "Строительный объект",
    },
    "en": {
        "window": "Window / frame",
        "wall": "Wall / slab",
        "roof": "Roof",
        "electrical": "Electrical panel / wiring",
        "facade": "Facade / exterior wall",
        "floor": "Floor / screed",
        "other": "Building element",
    },
}


# ── Prompts ──────────────────────────────────────────────────────────────────

_AUDIT_PROMPT = """
You are a certified thermographer and structural engineer with 15+ years of experience.
The user has submitted a photo (regular smartphone camera OR thermal/IR camera).
Respond in {language}.

Analyze the image and return ONLY a valid JSON object with this exact structure:
{{
  "object_type": "<window|wall|roof|electrical|facade|floor|other>",
  "risk_level": "<LOW|MEDIUM|HIGH|CRITICAL>",
  "risk_score": <float 0.0–1.0>,
  "temperature_observations": ["<observation>", "..."],
  "problems": [
    {{
      "type": "<moisture|mold|crack|thermal_bridge|electrical|structural|condensation|other>",
      "location": "<where in the image>",
      "severity": "<low|medium|high|critical>",
      "description": "<precise technical description>"
    }}
  ],
  "free_verdict": "<2-3 sentence expert summary — mention object type, main finding, risk level>",
  "premium_analysis": "<detailed physical explanation: root causes, what happens next if ignored, hidden secondary risks — 4-6 sentences>",
  "recommendations_brief": "<single most important action to take>",
  "recommendations_detailed": ["<step 1 with specifics>", "<step 2>", "<materials or specs needed>"],
  "premium_teaser": "<hint at what else was found without revealing details — create urgency, max 1 sentence>"
}}

Expertise rules:
- Regular camera: look for moisture stains, peeling paint/wallpaper (dew point inside wall), mold patches
  in corners (freezing bridge), condensation rings on windows, discoloration around electrical panels,
  efflorescence on masonry, crack patterns indicating structural vs. thermal movement.
- Thermal camera: analyze temperature gradients, identify cold bridges, hot spots, insulation gaps.
- Electrical panels: flag overheating terminals, uneven load distribution, scorch marks.
- Always provide temperature_observations even for regular photos (infer from visual clues).
- If image is clearly NOT a building or structure: return {{"error": "not_a_building",
  "free_verdict": "<polite message asking to send a building photo>"}}
- Return ONLY the JSON. No markdown, no explanation, no code fences.
""".strip()

_AUDIT_PROMPT_RU = _AUDIT_PROMPT.format(language="Russian")
_AUDIT_PROMPT_EN = _AUDIT_PROMPT.format(language="English")

_CALC_PROMPT = """
Ты — эксперт по энергоаудиту зданий.
Рассчитай теплопотери и экономический эффект диагностики.

Входные данные:
- Площадь: {area} м²
- Тип отопления: {heating}
- Расходы на отопление (самый холодный месяц): {payment} руб.
{weather_ctx}

Ответь СТРОГО в формате ниже.
Разрешённые HTML-теги: только <b> и <i>. Список — символ «•».

━━━━━━━━━━━━━━━━━━━━━

<b>📉 Расчётные теплопотери</b>
• Скрытые потери: <b>[X–Y]%</b> от общего потребления
• Ежемесячные потери: ~<b>[сумма] руб.</b> в холодный период
• Потери в год: ~<b>[сумма] руб.</b>

<b>💰 Окупаемость диагностики</b>
• Стоимость обследования: от <b>4 000 руб.</b>
• Срок окупаемости: <b>[расчёт]</b>
• Потенциальная экономия: ~<b>[сумма] руб./год</b> после устранения утечек

<b>📊 Вывод</b>
[1–2 предложения: конкретный вывод и призыв заказать диагностику]

━━━━━━━━━━━━━━━━━━━━━

Делай реальные расчёты (типовые потери 15–35%). Пиши по-русски, без воды.
""".strip()

_QC_PROMPT = """
Ты — строгий технический контролёр качества фотоотчётов инженерной компании «ИнфраСкан».
Инженер прислал снимок объекта для включения в официальный технический отчёт.

Оцени снимок по 4 критериям (0–25 баллов каждый):
1. ЧЁТКОСТЬ — снимок резкий, нет смазанности или дрожания камеры?
2. ОСВЕЩЁННОСТЬ — нормальная экспозиция? Не пересвечен, не слишком тёмный?
   (для тепловизора: видна ли шкала температур и цветовой градиент?)
3. ПОЛНОТА КАДРА — объект виден целиком? Правильный угол? Объект — главный в кадре?
4. РЕЛЕВАНТНОСТЬ — это строительный/инженерный объект?
   (окно, стена, щиток, кровля, фасад, труба, радиатор, фундамент и т.п.)

Верни ТОЛЬКО валидный JSON без markdown и объяснений:
{
  "sharpness": <0-25>,
  "exposure": <0-25>,
  "framing": <0-25>,
  "relevance": <0-25>,
  "total_score": <сумма 0-100>,
  "verdict": "<ПРИНЯТО|ЗАМЕЧАНИЕ|БРАК>",
  "reason": "<причина отказа или замечания одним предложением, null если ПРИНЯТО>",
  "tip": "<конкретный совет: отойди на X м, поверни камеру, выключи свет справа — null если total_score >= 80>",
  "object": "<что видно на снимке, 3-5 слов>"
}

Пороги вердикта:
- ПРИНЯТО: total_score >= 70
- ЗАМЕЧАНИЕ: total_score 50–69 (принято, но есть замечание для инженера)
- БРАК: total_score < 50 (пересъёмка обязательна)
""".strip()


# ── Core API calls ────────────────────────────────────────────────────────────


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def analyze_photo(
    data: bytes, locale: str = "ru", mime: str = "image/jpeg", context: str = ""
) -> dict:
    """Return structured analysis dict. Callers use format_analysis_free/premium to render."""
    if settings.gemini_stub:
        return _STUB_ANALYSIS
    prompt = _AUDIT_PROMPT_RU if locale == "ru" else _AUDIT_PROMPT_EN
    if context:
        prefix = (
            f"Контекст от пользователя (голосовое): {context}\n\n"
            if locale == "ru"
            else f"User context (voice): {context}\n\n"
        )
        prompt = prefix + prompt
    r = None
    try:
        r = await _generate_with_retry(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        parsed = json.loads(_strip_fences(r.text))
        outcome = "not_a_building" if parsed.get("error") == "not_a_building" else "ok"
        metrics.inc("photo_analysis_total", {"kind": "analyze", "outcome": outcome})
        return parsed
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON, wrapping as fallback")
        metrics.inc("photo_analysis_total", {"kind": "analyze", "outcome": "ok"})
        text = r.text if r is not None else "Analysis unavailable"
        return {
            "object_type": "other",
            "risk_level": "MEDIUM",
            "risk_score": 0.5,
            "temperature_observations": [],
            "problems": [],
            "free_verdict": text[:600],
            "premium_analysis": text,
            "recommendations_brief": "",
            "recommendations_detailed": [],
            "premium_teaser": "",
            "_fallback": True,
        }
    except Exception as e:
        logger.error("Gemini analyze_photo: %s", e)
        metrics.inc("photo_analysis_total", {"kind": "analyze", "outcome": "api_error"})
        msg = (
            "⚠️ Анализ временно недоступен. Попробуйте через минуту."
            if locale == "ru"
            else "⚠️ Analysis temporarily unavailable. Please try again in a minute."
        )
        return {"error": "api_error", "free_verdict": msg}


async def calculate_losses(area: float, heating: str, payment: float, weather_ctx: str = "") -> str:
    if settings.gemini_stub:
        return _STUB_LOSSES
    try:
        prompt = _CALC_PROMPT.format(
            area=area, heating=heating, payment=payment, weather_ctx=weather_ctx
        )
        r = await _generate_with_retry(
            model=settings.gemini_model,
            contents=prompt,
        )
        return r.text
    except Exception as e:
        logger.error("Gemini calculate_losses: %s", e)
        return "⚠️ Не удалось выполнить расчёт. Попробуйте позже."


async def check_quality(data: bytes, mime: str = "image/jpeg") -> dict:
    """QC check with score and actionable tip.

    Returns:
        ok      — True if ПРИНЯТО or ЗАМЕЧАНИЕ (photo is usable)
        score   — 0-100
        verdict — ПРИНЯТО | ЗАМЕЧАНИЕ | БРАК
        reason  — why rejected/flagged (str or None)
        tip     — specific improvement advice (str or None)
        object  — what object was detected (str)
    """
    if settings.gemini_stub:
        return _STUB_QC
    try:
        r = await _generate_with_retry(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), _QC_PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        parsed = json.loads(_strip_fences(r.text))
        score = min(100, max(0, int(parsed.get("total_score", 75))))
        verdict = parsed.get("verdict", "ПРИНЯТО")
        # Enforce score↔verdict consistency per prompt thresholds
        if score >= 70 and verdict == "БРАК":
            verdict = "ПРИНЯТО"
        elif score < 50 and verdict == "ПРИНЯТО":
            verdict = "БРАК"
        ok = verdict in ("ПРИНЯТО", "ЗАМЕЧАНИЕ")
        metrics.inc(
            "photo_analysis_total",
            {"kind": "quality", "outcome": "ok" if ok else "quality_reject"},
        )
        return {
            "ok": ok,
            "score": score,
            "verdict": verdict,
            "reason": parsed.get("reason"),
            "tip": parsed.get("tip"),
            "object": parsed.get("object", ""),
        }
    except Exception as e:
        logger.error("Gemini check_quality: %s", e)
        metrics.inc("photo_analysis_total", {"kind": "quality", "outcome": "api_error"})
        # fail-open: don't block engineer when API is down
        return {
            "ok": True,
            "score": 75,
            "verdict": "ПРИНЯТО",
            "reason": None,
            "tip": None,
            "object": "",
        }


# ── Formatters ────────────────────────────────────────────────────────────────


def format_analysis_free(result: dict, locale: str = "ru", stars: int = 150) -> str:
    if "error" in result:
        return result.get("free_verdict", "⚠️ Не удалось выполнить анализ.")

    risk = result.get("risk_level", "MEDIUM")
    emoji = _RISK_EMOJI.get(risk, "🟡")
    risk_lbl = _RISK_LABEL.get(locale, _RISK_LABEL["en"]).get(risk, risk)
    obj_lbl = _OBJECT_LABEL.get(locale, _OBJECT_LABEL["en"]).get(
        result.get("object_type", "other"), "Object"
    )
    verdict = result.get("free_verdict", "")
    rec = result.get("recommendations_brief", "")
    teaser = result.get("premium_teaser", "")

    if locale == "ru":
        return (
            f"🔬 <b>Анализ снимка</b>\n{_SEP}\n\n"
            f"🏠 <b>Объект:</b> {obj_lbl}\n"
            f"📊 <b>Риск:</b> {emoji} {risk_lbl}\n\n"
            f"{verdict}\n\n" + (f"💡 {rec}\n\n" if rec else "") + f"{_SEP}\n"
            f"🔒 <b>Premium-анализ выявил больше:</b>\n"
            f"<i>{teaser}</i>\n\n"
            f"⭐️ Разблокировать за <b>{stars} Stars</b> (~$1.5/мес)\n"
            f"Команда: /premium"
        )
    else:
        return (
            f"🔬 <b>Photo Analysis</b>\n{_SEP}\n\n"
            f"🏠 <b>Object:</b> {obj_lbl}\n"
            f"📊 <b>Risk:</b> {emoji} {risk_lbl}\n\n"
            f"{verdict}\n\n" + (f"💡 {rec}\n\n" if rec else "") + f"{_SEP}\n"
            f"🔒 <b>Premium analysis found more:</b>\n"
            f"<i>{teaser}</i>\n\n"
            f"⭐️ Unlock for <b>{stars} Stars</b> (~$1.5/month)\n"
            f"Command: /premium"
        )


def format_analysis_premium(result: dict, locale: str = "ru") -> str:
    if "error" in result:
        return result.get("free_verdict", "⚠️ Analysis failed.")

    risk = result.get("risk_level", "MEDIUM")
    emoji = _RISK_EMOJI.get(risk, "🟡")
    score = int(result.get("risk_score", 0.5) * 100)
    risk_lbl = _RISK_LABEL.get(locale, _RISK_LABEL["en"]).get(risk, risk)
    obj_lbl = _OBJECT_LABEL.get(locale, _OBJECT_LABEL["en"]).get(
        result.get("object_type", "other"), "Object"
    )

    problems = result.get("problems", [])
    temp_obs = result.get("temperature_observations", [])
    recs = result.get("recommendations_detailed", [])
    analysis = result.get("premium_analysis", result.get("free_verdict", ""))

    if locale == "ru":
        p_lines = ""
        for i, p in enumerate(problems[:5], 1):
            sev = _SEV_EMOJI.get(p.get("severity", "medium"), "🟠")
            p_lines += (
                f"\n{i}. {sev} <b>{p.get('description', '')}</b>\n   📍 {p.get('location', '')}\n"
            )

        t_lines = "\n".join(f"• {t}" for t in temp_obs[:3])
        r_lines = "\n".join(f"• {r}" for r in recs[:5])

        return (
            f"🔬 <b>Тепловизионный анализ</b> ⭐️\n{_SEP}\n\n"
            f"🏠 <b>Объект:</b> {obj_lbl}\n"
            f"📊 <b>Уровень риска:</b> {emoji} {risk_lbl} ({score}%)\n"
            + (f"\n🌡 <b>Температурная картина:</b>\n{t_lines}\n" if t_lines else "")
            + (f"\n⚠️ <b>Выявленные проблемы:</b>{p_lines}" if p_lines else "")
            + f"\n🧠 <b>Экспертный разбор:</b>\n{analysis}\n"
            + (f"\n💡 <b>План устранения:</b>\n{r_lines}" if r_lines else "")
        )
    else:
        p_lines = ""
        for i, p in enumerate(problems[:5], 1):
            sev = _SEV_EMOJI.get(p.get("severity", "medium"), "🟠")
            p_lines += (
                f"\n{i}. {sev} <b>{p.get('description', '')}</b>\n   📍 {p.get('location', '')}\n"
            )

        t_lines = "\n".join(f"• {t}" for t in temp_obs[:3])
        r_lines = "\n".join(f"• {r}" for r in recs[:5])

        return (
            f"🔬 <b>Thermal Analysis</b> ⭐️\n{_SEP}\n\n"
            f"🏠 <b>Object:</b> {obj_lbl}\n"
            f"📊 <b>Risk level:</b> {emoji} {risk_lbl} ({score}%)\n"
            + (f"\n🌡 <b>Temperature observations:</b>\n{t_lines}\n" if t_lines else "")
            + (f"\n⚠️ <b>Issues detected:</b>{p_lines}" if p_lines else "")
            + f"\n🧠 <b>Expert analysis:</b>\n{analysis}\n"
            + (f"\n💡 <b>Action plan:</b>\n{r_lines}" if r_lines else "")
        )


def format_analysis_text(result: dict) -> str:
    """Plain text version for employee reports (stored in Odoo)."""
    if "error" in result or "_fallback" in result:
        return result.get("free_verdict", result.get("premium_analysis", ""))
    return format_analysis_premium(result, locale="ru")


# ── Voice transcription ───────────────────────────────────────────────────────


async def transcribe_voice(audio_bytes: bytes, mime: str = "audio/ogg") -> str:
    """Transcribe a Telegram voice message to text using Gemini."""
    if settings.gemini_stub:
        return "Трещина в верхнем правом углу, видно намокание штукатурки"
    try:
        r = await _generate_with_retry(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime),
                "Transcribe this voice message verbatim into Russian. Return only the transcription text.",
            ],
        )
        return r.text.strip()
    except Exception as e:
        logger.error("Gemini transcribe_voice: %s", e)
        return ""


# ── WebApp data conversion ────────────────────────────────────────────────────

_SEV_TO_RISK = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"}
_TYPE_TO_ICON = {
    "thermal_bridge": "🌡",
    "moisture": "💧",
    "mold": "🟤",
    "crack": "🔩",
    "insulation": "🧱",
    "electrical": "⚡",
    "structural": "🏗",
    "condensation": "💧",
    "other": "⚠️",
}
_OBJTYPE_ICON = {
    "wall": "🧱",
    "window": "🪟",
    "roof": "🏠",
    "electrical": "⚡",
    "facade": "🏗",
    "floor": "🔲",
    "other": "📍",
}


def analysis_to_webapp(analysis: dict, scan_date: str = "") -> dict:
    """Convert Gemini analysis dict to the format expected by webapp/index.html."""
    from collections import defaultdict

    problems = analysis.get("problems", [])
    obj_type = analysis.get("object_type", "")
    obj_icon = _OBJTYPE_ICON.get(obj_type, "📍")
    sev_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    sev_labels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]

    zones_map: dict[str, list[str]] = defaultdict(list)
    zone_sev: dict[str, int] = defaultdict(int)

    for p in problems:
        loc = (p.get("location") or "Объект")[:30]
        sev = p.get("severity", "medium")
        zones_map[loc].append(p.get("description", ""))
        zone_sev[loc] = max(zone_sev[loc], sev_order.get(sev, 1))

    zones = [
        {
            "name": loc,
            "icon": _TYPE_TO_ICON.get(
                next(
                    (p.get("type", "") for p in problems if (p.get("location") or "")[:30] == loc),
                    "",
                ),
                obj_icon,
            ),
            "risk": sev_labels[zone_sev[loc]],
            "issues": issues,
        }
        for loc, issues in zones_map.items()
    ]

    if not zones:
        risk = analysis.get("risk_level", "MEDIUM")
        zones = [
            {
                "name": "Объект",
                "icon": obj_icon,
                "risk": risk,
                "issues": [analysis.get("free_verdict", "")[:120]],
            }
        ]

    score = analysis.get("risk_score", 0)
    if isinstance(score, float) and score <= 1.0:
        score = round(score * 100)  # round avoids 0.58*100=57.999...

    return {
        "risk_level": analysis.get("risk_level", "MEDIUM"),
        "risk_score": int(score),
        "object_type": _OBJECT_LABEL["ru"].get(obj_type, obj_type),
        "zones": zones,
        "free_verdict": analysis.get("free_verdict", ""),
        "scan_date": scan_date,
    }
