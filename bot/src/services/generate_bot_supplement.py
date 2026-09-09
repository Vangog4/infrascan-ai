"""Generator for official Supplement 3 (Дополнение № 3 к бизнес-плану — Telegram-бот)."""

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


class OfficialSupplementPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_draw_color(*_LINE_COLOR)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(2)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(0, 5, "Дополнение № 3 к бизнес-плану «ИнфраСкан AI» | ИП Гудков И.Г.", align="C")


def generate_bot_supplement():
    pdf = OfficialSupplementPDF()
    pdf.add_font("dj", "", _FONT_REG)
    pdf.add_font("dj", "B", _FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=18)
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

    # Subtitle tag
    pdf.set_font("dj", "B", 10)
    pdf.set_text_color(*_MUTED)
    pdf.cell(0, 5, "Приложение № 3 к бизнес-плану «ИнфраСкан AI»")
    pdf.ln(7)

    # Title
    pdf.set_font("dj", "B", 13)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 8, "ОБЪЯСНИТЕЛЬНАЯ ЗАПИСКА", align="C")
    pdf.ln(6)
    pdf.set_font("dj", "B", 10.5)
    pdf.multi_cell(
        0,
        5.5,
        "Тема: Внедрение Telegram-бота «ИнфраСкан AI» как цифровой платформы,\n"
        "обеспечения отказоустойчивости и дополнительного источника дохода",
        align="C",
    )
    pdf.ln(8)
    pdf.set_text_color(*_TEXT)

    # Section 1
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "1. Предмет и финансирование разработки (100% за свой счет)")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Настоящее дополнение фиксирует ввод в эксплуатацию цифрового сервиса на базе Telegram-бота «ИнфраСкан AI». "
        "Проектирование, программирование, интеграция ИИ и инфраструктурный запуск бота выполнены "
        "заявителем полностью (на 100%) за счет собственных средств. Средства государственной социальной "
        "помощи (социального контракта) на создание и обслуживание бота не расходовались и расходоваться не будут.",
    )
    pdf.ln(4)

    # Section 2
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "2. Обеспечение отказоустойчивости при блокировках и сбоях в РФ")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "В условиях риска блокировок зарубежных магазинов приложений (Google Play, App Store) и ограничений "
        "веб-сервисов в Российской Федерации Telegram-бот выступает в роли защищенного и автономного "
        "канала взаимодействия с клиентами и операторами:\n"
        "• Независимость от маркетплейсов: Бот не требует установки через зарубежные магазины приложений;\n"
        "• Работа в условиях слабой связи: Сообщения и фото загружаются даже при пониженном качестве мобильного интернета;\n"
        "• Гарантия непрерывности бизнеса: Клиенты сохраняют прямой доступ к оформлению заявок и получению заключения независимо от внешних сетевых блокировок.",
    )
    pdf.ln(4)

    # Section 3
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "3. Бот как дополнительный источник дохода")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Запуск бота формирует дополнительный самостоятельный поток выручки предприятию без пересмотра сметы:\n"
        "• Монетизация нейросетевых анализов (пакетная и подписочная модель Freemium);\n"
        "• Прием платежей в рублях непосредственно в чате (включая СБП и Telegram Stars);\n"
        "• Лидогенерация: конверсия первичных фотоэкспертиз пользователей в выездные комплексные услуги.",
    )
    pdf.ln(4)

    # Section 4
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "4. Отсутствие изменений в смете социального контракта")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Дополнение № 3 не влечет изменений перечня и сумм закупок по социальному контракту. "
        "Приобретенное оборудование (ноутбук Getac K120 и тепловизор) используется по прямому "
        "назначению. Создание бота расширяет коммерческий потенциал проекта без привлечения бюджета субсидии.",
    )
    pdf.ln(4)

    # Section 5
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "5. Заключительное положение")
    pdf.ln(7)
    pdf.set_text_color(*_TEXT)
    pdf.set_font("dj", "", 9.5)
    pdf.multi_cell(
        0,
        5.5,
        "Прошу приобщить настоящее Дополнение № 3 к материалам бизнес-плана проекта «ИнфраСкан AI» "
        "и учесть Telegram-бот как дополнительный источник дохода и средство обеспечения отказоустойчивости "
        "без пересмотра сметы социального контракта.",
    )
    # Section 6: QR Code
    pdf.set_font("dj", "B", 10.5)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(0, 7, "6. QR-код для быстрой проверки и доступа к Telegram-боту")
    pdf.ln(6)
    pdf.set_text_color(*_TEXT)

    qr_path = Path("/root/infrascan/docs/qr_codes/qr_telegram_bot.png")
    if qr_path.exists():
        y_qr = pdf.get_y()
        pdf.image(str(qr_path), x=12, y=y_qr, w=28)
        pdf.set_xy(43, y_qr + 2)
        pdf.set_font("dj", "B", 9.5)
        pdf.cell(0, 5, "Ссылка на бот: https://t.me/Infrascan_bot")
        pdf.ln(5)
        pdf.set_x(43)
        pdf.set_font("dj", "", 9)
        pdf.multi_cell(
            0,
            4.5,
            "Отсканируйте QR-код с помощью камеры мобильного телефона для мгновенного перехода "
            "и проверки работоспособности Telegram-бота «ИнфраСкан AI».",
        )
        pdf.set_y(y_qr + 30)
    else:
        pdf.ln(2)

    pdf.set_font("dj", "B", 10)
    pdf.cell(100, 6, "Индивидуальный предприниматель:")
    pdf.ln(8)
    y = pdf.get_y()
    pdf.set_font("dj", "", 9.5)
    pdf.cell(100, 6, "Гудков Иван Григорьевич   /_________________/")
    if _SIG.exists():
        pdf.image(str(_SIG), x=115, y=y - 8, w=32)

    out_a = Path(
        "/root/infrascan/docs/supplements_and_notes/dop_3_telegram_bot/дополнение_3_телеграмм_бот.pdf"
    )
    out_b = Path("/root/infrascan/docs/other/дополнение телеграмм бот.pdf")
    out_a.parent.mkdir(parents=True, exist_ok=True)
    out_b.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_a))
    pdf.output(str(out_b))
    print(f"Generated updated Supplement 3 with QR: {out_a}")


if __name__ == "__main__":
    generate_bot_supplement()
