import logging

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


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_AUDIT_PROMPT = """
Ты — эксперт по тепловизионной и строительной диагностике зданий.
Пользователь прислал фотографию (обычную или тепловизионную).

Проанализируй снимок и дай заключение СТРОГО в формате ниже.
Разрешённые HTML-теги: только <b> и <i>. Список — символ «•».
Никаких других тегов, никакого markdown.

━━━━━━━━━━━━━━━━━━━━━

<b>Объект:</b> [тип — окно / стена / электрощит / фасад / кровля / другое]

<b>🌡 Температурная картина</b>
• [конкретное наблюдение; если видны температуры — указывай °C]
• [наблюдение 2]
• [наблюдение 3 если есть]

<b>⚠️ Выявленные проблемы</b>
• [проблема или риск 1]
• [проблема или риск 2]
• [проблема или риск 3 если есть]

<b>📊 Уровень риска:</b> [НИЗКИЙ / СРЕДНИЙ / ВЫСОКИЙ / КРИТИЧЕСКИЙ]

<b>💡 Рекомендация</b>
[1–2 конкретных предложения — что сделать]

<i>До 80% теплопотерь скрыты от глаза — профессиональный тепловизор выявляет их до появления видимых повреждений.</i>

━━━━━━━━━━━━━━━━━━━━━

Пиши по-русски, кратко и конкретно — как эксперт на осмотре, а не как учебник.
Если снимок явно не относится к зданиям — вежливо попроси прислать фото объекта.
""".strip()

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
Ты — технический контролёр качества фотоотчётов инженерной компании.
Оцени качество приложенного снимка для включения в профессиональный технический отчёт.

Критерии:
1. Чёткость (не размыт ли снимок?)
2. Освещённость (не пересвечен / не слишком тёмный?)
3. Полнота кадра (виден ли объект целиком?)

Ответь СТРОГО в одном из двух форматов — без лишних слов:
- ПРИНЯТО
- БРАК: [причина одним предложением]
""".strip()


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

async def analyze_photo(data: bytes, mime: str = "image/jpeg") -> str:
    try:
        r = await _get().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), _AUDIT_PROMPT],
        )
        return r.text
    except Exception as e:
        logger.error("Gemini analyze_photo: %s", e)
        return "⚠️ Не удалось выполнить анализ. Попробуйте повторить позже."


async def calculate_losses(area: float, heating: str, payment: float) -> str:
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


async def check_quality(data: bytes, mime: str = "image/jpeg") -> tuple[bool, str]:
    try:
        r = await _get().aio.models.generate_content(
            model=settings.gemini_model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime), _QC_PROMPT],
        )
        text = r.text.strip()
        if text.startswith("ПРИНЯТО"):
            return True, ""
        reason = text.replace("БРАК:", "").replace("БРАК", "").strip()
        return False, reason or "Качество снимка неприемлемо для отчёта"
    except Exception as e:
        logger.error("Gemini check_quality: %s", e)
        return True, ""  # fail-open: don't block engineer on API error
