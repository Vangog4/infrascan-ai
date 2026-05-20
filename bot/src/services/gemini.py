"""
Gemini Vision service.

analyze_photo() returns a raw dict (JSON from Gemini).
Use format_analysis_free() / format_analysis_premium() to render for Telegram.
"""

import json
import logging
import re

from google import genai
from google.genai import types

from src.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


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


async def analyze_photo(data: bytes, locale: str = "ru", mime: str = "image/jpeg") -> dict:
    """Return structured analysis dict. Callers use format_analysis_free/premium to render."""
    if settings.gemini_stub:
        return _STUB_ANALYSIS
    prompt = _AUDIT_PROMPT_RU if locale == "ru" else _AUDIT_PROMPT_EN
    r = None
    try:
        r = await _get().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(_strip_fences(r.text))
    except json.JSONDecodeError:
        logger.warning("Gemini returned non-JSON, wrapping as fallback")
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
        msg = (
            "⚠️ Анализ временно недоступен. Попробуйте через минуту."
            if locale == "ru"
            else "⚠️ Analysis temporarily unavailable. Please try again in a minute."
        )
        return {"error": "api_error", "free_verdict": msg}


async def calculate_losses(area: float, heating: str, payment: float) -> str:
    if settings.gemini_stub:
        return _STUB_LOSSES
    try:
        prompt = _CALC_PROMPT.format(area=area, heating=heating, payment=payment)
        r = await _get().aio.models.generate_content(
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
        r = await _get().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), _QC_PROMPT],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        parsed = json.loads(_strip_fences(r.text))
        verdict = parsed.get("verdict", "ПРИНЯТО")
        return {
            "ok": verdict in ("ПРИНЯТО", "ЗАМЕЧАНИЕ"),
            "score": min(100, max(0, int(parsed.get("total_score", 75)))),
            "verdict": verdict,
            "reason": parsed.get("reason"),
            "tip": parsed.get("tip"),
            "object": parsed.get("object", ""),
        }
    except Exception as e:
        logger.error("Gemini check_quality: %s", e)
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
