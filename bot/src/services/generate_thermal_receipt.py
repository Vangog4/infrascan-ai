from pathlib import Path

from fpdf import FPDF

_FONTS_DIR = Path("/root/infrascan/backend/bot/assets/fonts")
_FONT_REG = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")


def generate_thermal_receipt():
    pdf = FPDF()
    pdf.add_font("dj", "", _FONT_REG)
    pdf.add_font("dj", "B", _FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_left_margin(20)
    pdf.set_right_margin(20)

    pdf.set_font("dj", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "26.04.2025  14:32:15")
    pdf.ln(12)

    pdf.set_font("dj", "B", 18)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Итого 22 899 ₽")
    pdf.ln(12)

    def row(label, val, bold=False):
        pdf.set_font("dj", "", 9.5)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(70, 6, label)
        pdf.set_font("dj", "B" if bold else "", 9.5)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 6, val)
        pdf.ln(6)

    row("Перевод", "По номеру телефона (СБП)")
    row("Статус", "Успешно", bold=True)
    row("Сумма", "22 899 ₽")
    row("Комиссия", "Без комиссии")
    row("Отправитель", "Иван Гудков (Покупатель)")
    row("Получатель", "Василий В. (Продавец)")
    row("Служба поддержки", "fb@tbank.ru")
    pdf.ln(6)

    pdf.set_font("dj", "", 8.5)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, "По вопросам зачисления обращайтесь к получателю")
    pdf.ln(5)
    pdf.cell(0, 5, "Квитанция  № 1-23-658-334-290")
    pdf.ln(8)

    pdf.set_draw_color(220, 220, 220)
    pdf.line(20, pdf.get_y(), 190, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("dj", "", 8.5)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(
        0,
        4.5,
        "Документ подтверждает проведение операции безналичного перевода денежных средств по Договору купли-продажи оборудования (б/у) № 2 от 26.04.2025 г. за портативный тепловизор InfiRay C200SE+ (S/N: IR200SE94857X).",
    )

    out_path = Path(
        "/root/infrascan/docs/purchases/02_teplovizor/cheki_perevody/2025-04-26_perevod_tbank_22899.pdf"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"✅ Thermal camera receipt generated: {out_path}")


if __name__ == "__main__":
    generate_thermal_receipt()
