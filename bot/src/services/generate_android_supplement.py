from pathlib import Path

from fpdf import FPDF

_FONTS_DIR = Path("/root/infrascan/backend/bot/assets/fonts")
_FONT_REG = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

_ACCENT = (230, 50, 50)  # Branded red for mobile app presentation
_TEXT = (40, 40, 40)
_MUTED = (100, 100, 100)
_LIGHT_BG = (250, 245, 245)
_LINE_COLOR = (230, 220, 220)


class AndroidReport(FPDF):
    def header(self):
        # Branded header top line
        self.set_fill_color(*_ACCENT)
        self.rect(0, 0, 210, 10, "F")
        self.set_y(15)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*_LINE_COLOR)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(2)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, "Мобильная платформа «InfraScan AI» (RuStore) | 2026", align="C")

    def page_title(self, text):
        self.set_font("dj", "B", 15)
        self.set_text_color(*_ACCENT)
        self.multi_cell(0, 8, text.upper())
        self.ln(5)

    def section_title(self, text):
        self.set_font("dj", "B", 12)
        self.set_text_color(*_ACCENT)
        self.cell(0, 8, text)
        self.ln(8)
        self.set_text_color(*_TEXT)

    def sub_section_title(self, text):
        self.set_font("dj", "B", 10)
        self.cell(0, 6, text)
        self.ln(6)

    def body_text(self, text):
        self.set_font("dj", "", 9.5)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, 5.5, text)
        self.ln(3)

    def bullet_point(self, title, desc):
        self.set_font("dj", "B", 9.5)
        self.set_text_color(*_TEXT)
        self.write(5.5, "• " + title + ": ")
        self.set_font("dj", "", 9.5)
        self.write(5.5, desc + "\n")
        self.ln(1)

    def highlight_box(self, text):
        self.set_fill_color(*_LIGHT_BG)
        self.set_font("dj", "", 9.5)
        self.set_text_color(*_TEXT)
        self.multi_cell(186, 5.5, text, fill=True, border=1)
        self.ln(4)


def main():
    pdf = AndroidReport()
    pdf.add_font("dj", "", _FONT_REG, uni=True)
    pdf.add_font("dj", "B", _FONT_BOLD, uni=True)

    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    # ─── Title Page ───
    pdf.page_title(
        "Дополнение к бизнес-плану проекта «ИнфраСкан AI»\nТема: Мобильная платформа экспресс-диагностики на базе ОС Android (RuStore)"
    )

    pdf.section_title("1. Назначение и концептуальная ценность")
    pdf.body_text(
        "В рамках технологического развития проекта «ИнфраСкан AI» разработано нативное мобильное приложение "
        "для операционной системы Android, предназначенное для публикации в российском магазине приложений RuStore. "
        "Приложение выступает как клиентский терминал экспресс-диагностики и рабочий инструмент выездных операторов. "
        "Оно обеспечивает бесшовное взаимодействие с портативными тепловизионными модулями (InfiRay, Seek Thermal, FLIR) "
        "и локальную обработку данных непосредственно на мобильном устройстве."
    )

    pdf.highlight_box(
        "Важность RuStore: Размещение приложения в RuStore решает проблему импортозамещения "
        "и исключает риски блокировок со стороны Google Play. Это обеспечивает прямой доступ "
        "к российской аудитории и безопасный прием платежей в рублях через встроенные библиотеки."
    )

    pdf.section_title("2. Интеграция с сервисами экосистемы RuStore")
    pdf.bullet_point(
        "RuStore Billing (Платежный модуль)",
        "Реализует безопасный прием платежей по картам «Мир» и через СБП. Внедрена подписочная модель монетизации (тарифы «Инженер» и «Бизнес») и покупка пакетов экспресс-сканирований.",
    )
    pdf.bullet_point(
        "RuStore Push SDK (Уведомления)",
        "Энергоэффективная доставка push-уведомлений о завершении сложных нейросетевых расчетов на сервере и статусах выездов.",
    )
    pdf.bullet_point(
        "RuStore App Update (Автообновления)",
        "Поддержка сценариев автоматического тихого обновления (Silent Mode) и принудительного обновления (Immediate Mode) для критических патчей.",
    )
    pdf.bullet_point(
        "RuStore Review SDK (Отзывы)",
        "Встроенная нативная форма для оценки приложения пользователями без перехода в маркет, повышающая рейтинг и охваты.",
    )

    pdf.add_page()  # Page 2

    pdf.section_title("3. Технические компоненты и функционал")

    pdf.sub_section_title("Технологический стек:")
    pdf.body_text(
        "Язык программирования: Kotlin 2.1. Интерфейс разработан на Jetpack Compose (UI). "
        "Обеспечена поддержка API 35 (Android 14/15) с обратной совместимостью до Android 8.0 (API 26)."
    )

    pdf.sub_section_title("Ключевые модули приложения:")
    pdf.bullet_point(
        "CameraX & Тепловизионный модуль",
        "Интеграция с портативными тепловизионными приставками по протоколу USB-OTG. Захват радиометрических данных в режиме реального времени.",
    )
    pdf.bullet_point(
        "ML Kit Text Recognition (Локальный OCR)",
        "Встроенная локальная библиотека оптического распознавания текста (OCR) от Google/Huawei. Автоматически распознает показатели датчиков оборудования, серийные номера щитков и счетчиков непосредственно на устройстве без интернета.",
    )
    pdf.bullet_point(
        "Авторизация VK ID SDK",
        "Удобный вход в один клик (One Tap) с возможностью верификации профилей через Госуслуги, что повышает доверие пользователей.",
    )
    pdf.bullet_point(
        "MediaProjection API",
        "Обеспечивает захват экрана для удаленной поддержки оператора инженером или записи видео процесса сканирования.",
    )
    pdf.bullet_point(
        "AccessibilityService",
        "Используется в сценариях автоматизации и удаленного администрирования для интеграции с внешними аппаратными комплексами.",
    )

    pdf.ln(2)
    pdf.section_title("4. Бизнес-модель и монетизация")

    pdf.bullet_point(
        "Розничные сканирования (Freemium)",
        "Обычные владельцы квартир могут скачать приложение бесплатно, получить 3 базовых сканирования. Дополнительные глубокие отчеты приобретаются поштучно (пакетами по 3 и 10 сканирований).",
    )
    pdf.bullet_point(
        "Профессиональные подписки",
        "Для строителей и прорабов внедрены месячные тарифы, снимающие лимиты на число ИИ-анализов и открывающие экспорт отчетов в PDF/Odoo.",
    )
    pdf.bullet_point(
        "Поставка оборудования в комплекте",
        "Возможность продажи готовых B2B-комплектов: rugged-смартфон (Kyocera Torque 5G) + тепловизионный модуль (InfiRay) + предустановленное приложение.",
    )

    pdf.ln(4)
    pdf.section_title("5. QR-код для проверки и скачивания в RuStore")
    qr_path = Path("/root/infrascan/docs/qr_codes/qr_rustore_app.png")
    if qr_path.exists():
        y_qr = pdf.get_y()
        pdf.image(str(qr_path), x=12, y=y_qr, w=28)
        pdf.set_xy(43, y_qr + 2)
        pdf.set_font("dj", "B", 9.5)
        pdf.cell(0, 5, "Ссылка в RuStore: https://apps.rustore.ru/app/com.infrascan.ai")
        pdf.ln(5)
        pdf.set_x(43)
        pdf.set_font("dj", "", 9)
        pdf.multi_cell(
            0,
            4.5,
            "Отсканируйте QR-код камерой телефона для быстрой загрузки и проверки страницы "
            "мобильного приложения «InfraScan AI» в российском магазине приложений RuStore.",
        )
        pdf.set_y(y_qr + 30)

    out_a = Path(
        "/root/infrascan/docs/supplements_and_notes/dop_4_android_app/дополнение мобильное приложение.pdf"
    )
    out_b = Path("/root/infrascan/docs/other/дополнение мобильное приложение.pdf")
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_a))
    pdf.output(str(out_b))
    print(f"✅ PDF successfully generated at: {out_a}")


if __name__ == "__main__":
    main()
