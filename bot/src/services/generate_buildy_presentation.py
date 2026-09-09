"""Generator for multi-page visual presentation of Buildy app & UI design (Дополнение № 5)."""

from pathlib import Path

from fpdf import FPDF

_FONTS_DIR = Path("/root/infrascan/backend/bot/assets/fonts")
_FONT_REG = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

_ACCENT = (245, 124, 0)  # Branded Buildy Orange
_DARK_BG = (28, 28, 30)
_TEXT = (40, 40, 40)
_MUTED = (100, 100, 100)
_LINE_COLOR = (220, 224, 230)

_SIG = Path("/root/infrascan/docs/other/signature.png")
_MOCKUPS_DIR = Path("/root/infrascan/docs/supplements_and_notes/dop_5_buildy_app/ui_mockups")


class BuildyPresentationPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*_LINE_COLOR)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(2)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(
            0,
            5,
            "Приложение «Buildy» (технология «Кибер-прораб») | Дополнение № 5 к бизнес-плану",
            align="C",
        )


def generate_presentation():
    pdf = BuildyPresentationPDF()
    pdf.add_font("dj", "", _FONT_REG)
    pdf.add_font("dj", "B", _FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=18)

    # ─── PAGE 1: Header + Description ───
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    # Header right aligned
    pdf.set_font("dj", "", 9.5)
    pdf.cell(110, 5, "")
    pdf.cell(0, 5, "Руководителю ТУ МСР ПК по Чайковскому г.о.", align="R")
    pdf.ln(5)
    pdf.cell(110, 5, "")
    pdf.cell(0, 5, "Сафоновой Н.Г.", align="R")
    pdf.ln(5)
    pdf.cell(110, 5, "")
    pdf.cell(0, 5, "от ИП Гудкова Ивана Григорьевича", align="R")
    pdf.ln(8)

    pdf.set_font("dj", "B", 10)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, "Приложение № 5 к бизнес-плану «ИнфраСкан AI»")
    pdf.ln(7)

    pdf.set_font("dj", "B", 13)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 8, "ДОПОЛНЕНИЕ № 5 К БИЗНЕС-ПЛАНУ", align="C")
    pdf.ln(6)
    pdf.set_font("dj", "B", 10.5)
    pdf.multi_cell(
        0,
        5.5,
        "Тема: Мобильная платформа «Buildy» (второй контур «Кибер-прораба»)\n"
        "Спецификация, интерфейс и макеты UI-дизайна",
        align="C",
    )
    pdf.ln(8)
    pdf.set_text_color(*_TEXT)

    # Section 1
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "1. Назначение и концепция сервиса")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Мобильное приложение «Buildy» разрабатывается как расширение экосистемы «ИнфраСкан AI» "
        "на технологии «Кибер-прораб». Если основной контур («ИнфраСкан AI») выявляет дефекты объектов "
        "с помощью тепловизора, то «Buildy» решает задачу «как рассчитать, замерить и заактировать работы». "
        "Приложение создается заявителем за свой счет, без привлечения средств социального контракта.",
    )
    pdf.ln(4)

    # Section 2
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "2. Ключевые модули и функциональные возможности")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)

    def bp(title, desc):
        pdf.set_font("dj", "B", 9.5)
        pdf.write(5.5, "• " + title + ": ")
        pdf.set_font("dj", "", 9.5)
        pdf.write(5.5, desc + "\n")
        pdf.ln(1.5)

    bp(
        "Строительные калькуляторы (20+)",
        "Быстрый расчет материалов и смет с привязкой к региональным базам цен (сценарий «Баня за 30 секунд»).",
    )
    bp(
        "AI-ассистент с RAG (СП / ГОСТ / ПУЭ)",
        "Ответы на нормативные вопросы с обязательной точной цитатой пункта строительных правил. Галлюцинации блокируются валидацией базы.",
    )
    bp(
        "Полевые инструменты (AR & Цифровой уровень)",
        "Точное измерение углов (+-0.1°) и расстояний камерой смартфона. Работает офлайн без профессионального геодезического прибора.",
    )
    bp(
        "Голосовой сметный ввод",
        "Преобразование фразы «добавь 40 метров кабеля 3х2,5» в строчку сметы непосредственно во время работы на объекте.",
    )
    pdf.ln(4)

    # ─── PAGE 2: UI Design Showcase (Mockups) ───
    pdf.add_page()
    pdf.set_font("dj", "B", 12)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "3. Визуальная демонстрация UI-дизайна и интерфейсов", align="C")
    pdf.ln(8)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5,
        "Интерфейс «Buildy» спроектирован по стандарту UX/UI (45 экранов), включает обязательную "
        "Тёмную тему (Dark Mode), карточки 16px, шрифты Inter, skeleton-лоадеры и тактильный виброотклик (Haptic Feedback).",
        align="C",
    )
    pdf.ln(6)

    # Display 3 mockups side by side
    calc_path = _MOCKUPS_DIR / "calc_screen.jpg"
    chat_path = _MOCKUPS_DIR / "chat_screen.jpg"
    tool_path = _MOCKUPS_DIR / "tools_screen.jpg"

    y_pos = pdf.get_y()
    img_w = 58
    gap = 6

    if calc_path.exists():
        pdf.image(str(calc_path), x=12, y=y_pos, w=img_w)
    if chat_path.exists():
        pdf.image(str(chat_path), x=12 + img_w + gap, y=y_pos, w=img_w)
    if tool_path.exists():
        pdf.image(str(tool_path), x=12 + (img_w + gap) * 2, y=y_pos, w=img_w)

    pdf.set_y(y_pos + 105)
    pdf.set_font("dj", "B", 9)
    pdf.cell(img_w + gap, 5, "Экран 1: Калькулятор смет", align="C")
    pdf.cell(img_w + gap, 5, "Экран 2: AI-чат с ГОСТ/СП", align="C")
    pdf.cell(img_w, 5, "Экран 3: AR-уровень (+-0.1°)", align="C")
    pdf.ln(10)

    # Section 4
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "4. Монетизация и отсутствие изменений в смете")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Разработка приложения «Buildy» осуществляется полностью за счет собственных средств заявителя. "
        "Средства социального контракта на Buildy не направлялись. Сервис выступает как дополнительный "
        "источник дохода (подписки, триал, платные пакеты) и расширяет коммерческий потенциал проекта.",
    )
    pdf.ln(10)

    pdf.set_font("dj", "B", 10)
    pdf.cell(100, 6, "Индивидуальный предприниматель:")
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 6, "Гудков Иван Григорьевич   /_________________/")
    if _SIG.exists():
        pdf.image(str(_SIG), x=115, y=y - 8, w=32)

    out_a = Path(
        "/root/infrascan/docs/supplements_and_notes/dop_5_buildy_app/дополнение_5_презентация_Buildy.pdf"
    )
    out_b = Path("/root/infrascan/docs/other/дополнение_5_презентация_Buildy.pdf")
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_a))
    pdf.output(str(out_b))
    print(f"Generated Buildy visual presentation: {out_a}")


if __name__ == "__main__":
    generate_presentation()
