"""Generator for clean, official versions of Дополнение 2 and Объяснительная (сроки)."""

from pathlib import Path

from fpdf import FPDF

_FONTS_DIR = Path("/root/infrascan/backend/bot/assets/fonts")
_FONT_REG = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

_ACCENT = (0, 102, 204)
_TEXT = (40, 40, 40)
_MUTED = (100, 100, 100)
_LINE_COLOR = (220, 224, 230)

_SIG = Path("/root/infrascan/docs/other/signature.png")


class OfficialDocPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*_LINE_COLOR)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(2)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, "ИП Гудков И.Г. | Проект «ИнфраСкан AI» | 2026", align="C")


def generate_dop2():
    """Generate Дополнение 2.pdf (Акт ввода InfraScan OS) without template placeholders."""
    pdf = OfficialDocPDF()
    pdf.add_font("dj", "", _FONT_REG, uni=True)
    pdf.add_font("dj", "B", _FONT_BOLD, uni=True)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    # Header / Approval block
    pdf.set_font("dj", "B", 10)
    pdf.cell(100, 5, "ДОКУМЕНТ 2: Акт о выполненных работах")
    pdf.cell(0, 5, "УТВЕРЖДАЮ", align="R")
    pdf.ln(5)
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 5, "(Доказательство реализации)")
    pdf.cell(0, 5, "Индивидуальный предприниматель", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "____________ / Гудков И.Г. /", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "«16» августа 2026 г.", align="R")
    pdf.ln(10)

    # Title
    pdf.set_font("dj", "B", 13)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 8, "АКТ ВВОДА В ОПЫТНО-ПРОМЫШЛЕННУЮ ЭКСПЛУАТАЦИЮ", align="C")
    pdf.ln(6)
    pdf.set_font("dj", "B", 11)
    pdf.cell(0, 6, "аппаратно-программного комплекса «InfraScan OS»", align="C")
    pdf.ln(10)
    pdf.set_text_color(*_TEXT)

    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Настоящий акт составлен о том, что в период с апреля 2025 г. по август 2026 г. "
        "индивидуальным предпринимателем Гудковым И.Г. были проведены работы по разработке, "
        "настройке и запуску цифровой инфраструктуры предприятия.",
    )
    pdf.ln(4)

    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "Перечень выполненных и внедренных работ:")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)

    def bp(title, desc):
        pdf.set_font("dj", "B", 9.5)
        pdf.write(5.5, "• " + title + ": ")
        pdf.set_font("dj", "", 9.5)
        pdf.write(5.5, desc + "\n")
        pdf.ln(1.5)

    bp(
        "Разработка веб-представительства (Сайта)",
        "Зарегистрирован домен infrascan-ai.ru. Разработан дизайн и структура сайта, настроен защищенный протокол передачи данных (SSL-сертификат). Внедрена «Умная анкета» заказчика: модуль интерактивного сбора данных об объекте (площадь, этажность, материал стен) для предварительного расчета стоимости.",
    )
    bp(
        "Внедрение ERP-системы Odoo 19",
        "Развернута локальная база данных и модуль управления клиентами (CRM). Настроена сквозная воронка продаж: от первичной заявки с сайта/бота до выставления счета и формирования акта выполненных работ.",
    )
    bp(
        "Интеграция с нейросетевым модулем Gemini",
        "Подключен и протестирован модуль ИИ для автоматического распознавания термограмм и подготовки первичных отчетов. Скорость первичной обработки заявок сокращена с 2 часов до 5 минут.",
    )
    bp(
        "Подготовка мобильной рабочей станции Getac K120",
        "Ноутбук Getac K120 (S/N: RK67D4895X) настроен в качестве единого командного пункта руководителя и станции работы с ЭДО/СБИС.",
    )

    pdf.ln(4)
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "Заключение:")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)

    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Цифровая платформа InfraScan OS прошла успешное тестирование, признана полностью "
        "работоспособной и введена в эксплуатацию. Указанные работы выполнены самостоятельно, "
        "за счет собственных ресурсов и без привлечения дополнительных средств социального контракта.",
    )
    pdf.ln(12)

    pdf.set_font("dj", "B", 10)
    pdf.cell(100, 6, "Индивидуальный предприниматель:")
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 6, "Гудков Иван Григорьевич   /_________________/")
    if _SIG.exists():
        pdf.image(str(_SIG), x=115, y=y - 8, w=32)

    out_a = Path("/root/infrascan/docs/supplements_and_notes/dop_2_akt_vvoda/Дополнение 2.pdf")
    out_b = Path("/root/infrascan/docs/other/Дополнение 2.pdf")
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_a))
    pdf.output(str(out_b))
    print(f"Generated: {out_a}")


def generate_obyasnitelnaya():
    """Generate Объяснительная .pdf (сроки отчётности) without template placeholders."""
    pdf = OfficialDocPDF()
    pdf.add_font("dj", "", _FONT_REG, uni=True)
    pdf.add_font("dj", "B", _FONT_BOLD, uni=True)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_left_margin(12)
    pdf.set_right_margin(12)

    # Header right aligned
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "Руководителю ТУ МСР ПК по Чайковскому г.о.", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "Сафоновой Н.Г.", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "от ИП Гудкова Ивана Григорьевича", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "Адрес: Пермский край, г. Чайковский,", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "п. Векошинка, ул. Центральная, д. 7", align="R")
    pdf.ln(5)
    pdf.cell(100, 5, "")
    pdf.cell(0, 5, "Тел.: 8 (922) 316-94-40", align="R")
    pdf.ln(10)

    # Title
    pdf.set_font("dj", "B", 12)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "ОБЪЯСНИТЕЛЬНАЯ ЗАПИСКА", align="C")
    pdf.ln(6)
    pdf.set_font("dj", "B", 10)
    pdf.cell(0, 6, "о причине задержки предоставления отчетности", align="C")
    pdf.ln(6)
    pdf.cell(0, 6, "и ходатайство о продлении сроков реализации социального контракта", align="C")
    pdf.ln(10)
    pdf.set_text_color(*_TEXT)

    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Я, Гудков Иван Григорьевич, являясь получателем государственной социальной помощи "
        "на основании социального контракта, настоящим поясняю причины задержки предоставления "
        "отчетности по целевому расходованию средств (чеков) и отчета о проделанной работе.\n\n"
        "Нарушение сроков вызвано совокупностью объективных обстоятельств и внешних факторов, "
        "влияющих на ведение деятельности в месте моего проживания (п. Векошинка), а именно:\n\n"
        "1. Проблемы со связью и электроснабжением. Нестабильное интернет-покрытие и частые "
        "перебои в электросети затрудняли своевременную выгрузку документации и сдачу отчетных форм.\n\n"
        "2. Переход на цифровую платформу InfraScan OS. В процессе работы потребовалась существенная "
        "модернизация бизнес-модели: создание веб-ресурса, Telegram-бота и системы автоматизированного "
        "учета Odoo 19 для удаленного взаимодействия с клиентами.\n\n"
        "3. Сложности с получением кассовых чеков. Часть оборудования (включая защищенную станцию Getac K120) "
        "приобреталась у частных лиц (б/у), в связи с чем предоставление кассовых чеков ККТ невозможно, "
        "и подтверждение оплаты осуществляется ДКП, актом приёма-передачи и банковской квитанцией (СБП/Т-Банк).\n\n"
        "Учитывая изложенное, прошу продлить срок предоставления итоговой отчетности и приобщить "
        "предоставляемый комплект документов к материалам социального контракта.",
    )
    pdf.ln(12)

    pdf.set_font("dj", "B", 10)
    pdf.cell(100, 6, "Индивидуальный предприниматель:")
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 6, "Гудков Иван Григорьевич   /_________________/")
    if _SIG.exists():
        pdf.image(str(_SIG), x=115, y=y - 8, w=32)

    out_a = Path(
        "/root/infrascan/docs/supplements_and_notes/00_general_and_timing/Объяснительная .pdf"
    )
    out_b = Path("/root/infrascan/docs/other/Объяснительная .pdf")
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_a))
    pdf.output(str(out_b))
    print(f"Generated: {out_a}")


if __name__ == "__main__":
    generate_dop2()
    generate_obyasnitelnaya()
