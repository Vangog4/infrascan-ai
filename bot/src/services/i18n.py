"""Simple key-value translations for 5 locales: ru, en, de, tr, kk."""

_STRINGS: dict[str, dict[str, str]] = {
    # ── Onboarding ──────────────────────────────────────────────────────────
    "onb_welcome": {
        "ru": (
            "👋 <b>Добро пожаловать в InfraScan AI!</b>\n\n"
            "Я анализирую фотографии зданий и выявляю:\n"
            "• Тепловые утечки и мостики холода\n"
            "• Дефекты кровли, окон, стен\n"
            "• Риски для безопасности\n\n"
            "Просто отправьте фото — результат за 30 секунд."
        ),
        "en": (
            "👋 <b>Welcome to InfraScan AI!</b>\n\n"
            "I analyze building photos and detect:\n"
            "• Heat leaks and cold bridges\n"
            "• Roof, window, wall defects\n"
            "• Safety risks\n\n"
            "Just send a photo — result in 30 seconds."
        ),
        "de": (
            "👋 <b>Willkommen bei InfraScan AI!</b>\n\n"
            "Ich analysiere Gebäudefotos und erkenne:\n"
            "• Wärmeverluste und Kältebrücken\n"
            "• Dach-, Fenster- und Wandschäden\n"
            "• Sicherheitsrisiken\n\n"
            "Senden Sie einfach ein Foto — Ergebnis in 30 Sekunden."
        ),
        "tr": (
            "👋 <b>InfraScan AI'ye Hoş Geldiniz!</b>\n\n"
            "Bina fotoğraflarını analiz ederek tespit ediyorum:\n"
            "• Isı kayıpları ve soğuk köprüler\n"
            "• Çatı, pencere, duvar kusurları\n"
            "• Güvenlik riskleri\n\n"
            "Sadece bir fotoğraf gönderin — 30 saniyede sonuç."
        ),
        "kk": (
            "👋 <b>InfraScan AI-ге қош келдіңіз!</b>\n\n"
            "Мен ғимарат суреттерін талдап анықтаймын:\n"
            "• Жылу ағындары мен суық көпірлер\n"
            "• Шатыр, терезе, қабырға ақаулары\n"
            "• Қауіпсіздік тәуекелдері\n\n"
            "Жай сурет жіберіңіз — 30 секундта нәтиже."
        ),
    },
    # ── Photo audit prompt ───────────────────────────────────────────────────
    "audit_prompt": {
        "ru": (
            "📷 Отправьте фото объекта — окно, стена, щиток, кровля или фасад.\n\n"
            "<i>ИИ проанализирует снимок и выдаст заключение с уровнем риска за 30 секунд.</i>"
        ),
        "en": (
            "📷 Send a photo of the object — window, wall, electrical panel, roof or facade.\n\n"
            "<i>AI will analyze it and return a risk assessment in ~30 seconds.</i>"
        ),
        "de": (
            "📷 Senden Sie ein Foto des Objekts — Fenster, Wand, Sicherungskasten, Dach oder Fassade.\n\n"
            "<i>Die KI analysiert es und liefert eine Risikobewertung in ~30 Sekunden.</i>"
        ),
        "tr": (
            "📷 Nesnenin fotoğrafını gönderin — pencere, duvar, sigorta kutusu, çatı veya cephe.\n\n"
            "<i>Yapay zeka ~30 saniyede risk değerlendirmesi döndürür.</i>"
        ),
        "kk": (
            "📷 Объект суретін жіберіңіз — терезе, қабырға, электр щиты, шатыр немесе фасад.\n\n"
            "<i>ЖИ ~30 секундта тәуекел бағалауын қайтарады.</i>"
        ),
    },
    # ── Daily limit message ──────────────────────────────────────────────────
    "limit_reached": {
        "ru": "⚠️ <b>Дневной лимит исчерпан</b>.\n\nЛимит обновится в полночь по UTC или подключите Premium — безлимитный анализ за <b>150 Stars/мес</b>.\n\n👉 /premium",
        "en": "⚠️ <b>Daily limit reached</b>.\n\nLimit resets at midnight UTC, or get Premium — unlimited analysis for <b>150 Stars/month</b>.\n\n👉 /premium",
        "de": "⚠️ <b>Tageslimit erreicht</b>.\n\nLimit wird um Mitternacht UTC zurückgesetzt oder holen Sie Premium — unbegrenzte Analyse für <b>150 Stars/Monat</b>.\n\n👉 /premium",
        "tr": "⚠️ <b>Günlük limit doldu</b>.\n\nLimit UTC gece yarısı sıfırlanır veya Premium alın — <b>150 Stars/ay</b> için sınırsız analiz.\n\n👉 /premium",
        "kk": "⚠️ <b>Күндік лимит таусылды</b>.\n\nЛимит UTC түнгі 12-де жаңарады немесе Premium алыңыз — <b>150 Stars/ай</b> үшін шектеусіз талдау.\n\n👉 /premium",
    },
    # ── Analyzing message ────────────────────────────────────────────────────
    "analyzing": {
        "ru": "🔍 Анализирую снимок...",
        "en": "🔍 Analyzing photo...",
        "de": "🔍 Foto wird analysiert...",
        "tr": "🔍 Fotoğraf analiz ediliyor...",
        "kk": "🔍 Сурет талдануда...",
    },
    # ── Cancel ───────────────────────────────────────────────────────────────
    "cancelled": {
        "ru": "❌ Отменено.",
        "en": "❌ Cancelled.",
        "de": "❌ Abgebrochen.",
        "tr": "❌ İptal edildi.",
        "kk": "❌ Бас тартылды.",
    },
}

# Locales that fall back to EN for handlers not yet translated
_FALLBACK = "en"


def t(key: str, locale: str) -> str:
    """Return translated string for key+locale, falling back to EN."""
    lang = locale if locale in ("ru", "en", "de", "tr", "kk") else _FALLBACK
    entry = _STRINGS.get(key, {})
    return entry.get(lang) or entry.get(_FALLBACK, key)
