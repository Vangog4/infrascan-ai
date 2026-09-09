"""Обоснование выбора и план модернизации Getac K120 — станция управления проектом."""

from pathlib import Path

from fpdf import FPDF

_FONTS_DIR = Path("/root/infrascan/backend/bot/assets/fonts")
_FONT_REG = str(_FONTS_DIR / "DejaVuSans.ttf")
_FONT_BOLD = str(_FONTS_DIR / "DejaVuSans-Bold.ttf")

_ACCENT = (0, 102, 204)
_TEXT = (40, 40, 40)
_MUTED = (100, 100, 100)
_LINE = (220, 224, 230)
_FILL = (240, 245, 250)

_OUT_A = Path("/root/infrascan/docs/other/акт_модернизации_getac.pdf")
_OUT_B = Path(
    "/root/infrascan/docs/purchases/01_noutbuk_getac_k120/dogovor/акт_модернизации_getac.pdf"
)
_SIG = Path("/root/infrascan/docs/other/signature.png")


class ActPDF(FPDF):
    def header(self):
        self.set_fill_color(*_ACCENT)
        self.rect(0, 0, 210, 7, "F")
        self.set_y(10)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(
            0,
            4,
            "Проект «ИнфраСкан AI»  ·  ИП Гудков И.Г.",
            align="C",
        )
        self.ln(3)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*_LINE)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(2)
        self.set_font("dj", "", 8)
        self.set_text_color(*_MUTED)
        self.cell(
            0,
            4,
            f"План модернизации рабочей станции управления проектом  ·  стр. {self.page_no()}",
            align="C",
        )

    def h1(self, text):
        self.set_font("dj", "B", 13)
        self.set_text_color(*_ACCENT)
        self.multi_cell(0, 7, text, align="C")
        self.ln(2)
        self.set_text_color(*_TEXT)

    def h2(self, text):
        self.ln(2)
        self.set_font("dj", "B", 10.5)
        self.set_text_color(*_ACCENT)
        self.cell(0, 7, text)
        self.ln(7)
        self.set_text_color(*_TEXT)

    def body(self, text, size=9.4, lh=5.1):
        self.set_font("dj", "", size)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, lh, text)
        self.ln(1.5)

    def bold_body(self, text, size=9.4, lh=5.1):
        self.set_font("dj", "B", size)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, lh, text)
        self.ln(1)

    def bullet(self, title, desc):
        self.set_font("dj", "B", 9.3)
        self.set_text_color(*_TEXT)
        self.write(5.1, "• " + title + ". ")
        self.set_font("dj", "", 9.3)
        self.write(5.1, desc + "\n")
        self.ln(0.8)

    def kv_table(self, rows):
        col_w = (55, 125)
        lh = 5.2
        self.set_draw_color(*_LINE)
        for i, (k, v) in enumerate(rows):
            self.set_font("dj", "B", 8.8)
            h_k = self.get_string_width(k) / col_w[0]
            self.set_font("dj", "", 8.8)
            # rough line count for value
            words = v.split()
            line = ""
            n = 1
            for w in words:
                trial = (line + " " + w).strip()
                if self.get_string_width(trial) > col_w[1] - 2:
                    n += 1
                    line = w
                else:
                    line = trial
            n = max(n, max(1, int(h_k) + 1))
            need = n * lh + 2
            if self.get_y() + need > 275:
                self.add_page()
            fill = i % 2 == 0
            if fill:
                self.set_fill_color(*_FILL)
            y = self.get_y()
            self.set_font("dj", "B", 8.8)
            self.set_text_color(*_TEXT)
            self.multi_cell(col_w[0], lh, k, border=0, fill=fill)
            h1 = self.get_y() - y
            self.set_xy(15 + col_w[0], y)
            self.set_font("dj", "", 8.8)
            self.multi_cell(col_w[1], lh, v, border=0, fill=fill)
            h2 = self.get_y() - y
            h = max(h1, h2, lh)
            self.set_xy(15, y)
            self.cell(col_w[0], h, "", border=1)
            self.cell(col_w[1], h, "", border=1)
            self.set_y(y + h)
        self.ln(3)


def build():
    pdf = ActPDF()
    pdf.add_font("dj", "", _FONT_REG)
    pdf.add_font("dj", "B", _FONT_BOLD)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)

    pdf.h1("ОБОСНОВАНИЕ ВЫБОРА И ПЛАН МОДЕРНИЗАЦИИ")
    pdf.set_font("dj", "B", 11)
    pdf.set_text_color(*_ACCENT)
    pdf.multi_cell(
        0,
        6,
        "Рабочая станция внутреннего управления проектом\nGetac K120  ·  «ИнфраСкан AI»",
        align="C",
    )
    pdf.ln(3)
    pdf.set_font("dj", "", 9.4)
    pdf.set_text_color(*_TEXT)
    pdf.cell(95, 5, "г. Чайковский")
    pdf.cell(0, 5, "«16» августа 2026 г.", align="R")
    pdf.ln(8)

    pdf.body(
        "Документ объясняет, зачем проекту защищённый компьютер Getac K120 "
        "и как его настраиваем. Это рабочее место руководителя: серверы, "
        "сайты, боты, СБИС, ремонт и администрирование."
    )

    pdf.h2("1. Назначение в проекте")
    pdf.body(
        "После корректировки бизнес-модели проект опирается на IT-платформу: "
        "сайт, Telegram-бот, ERP Odoo, серверная инфраструктура, электронный "
        "документооборот ИП. Стационарного офиса с гарантированной связью нет "
        "(д. Векошинка, перебои сети). Нужен полноценный Windows-компьютер, "
        "который едет с руководителем и держит доступ к внутреннему контуру "
        "даже без домашнего интернета."
    )
    pdf.bullet(
        "Серверы и инфраструктура",
        "подключение к VDS, контейнеры, логи, перезапуск сервисов, бэкапы, "
        "контроль что сайт и бот живы.",
    )
    pdf.bullet(
        "Сайты",
        "правка витрины и посадочных, проверка вёрстки, устранение сбоев, "
        "публикация материалов — работа, которую со смартфона не сделать.",
    )
    pdf.bullet(
        "Боты и ERP",
        "админка Telegram-бота, проверка сценариев инженера/клиента, Odoo "
        "(заявки, отчёты, справочники).",
    )
    pdf.bullet(
        "Отчётность ИП через СБИС",
        "сдача деклараций, ЭДО, квалифицированная подпись. СБИС требует "
        "полноценный Windows и криптопровайдер — телефон и планшет на Android "
        "эту обязанность не закрывают.",
    )
    pdf.bullet(
        "Внутреннее управление",
        "договоры, сканы закупок, переписка с комиссией, финансовая модель, "
        "календарь работ — весь контур «ведения проекта» в одном защищённом ПК.",
    )

    pdf.h2("2. Что это за устройство")
    pdf.body(
        "Getac K120 — защищённый промышленный ноутбук-трансформер (2-в-1) "
        "класса fully rugged на Windows. По ДКП № 1 от 26.04.2025 (б/у): "
        "16 ГБ ОЗУ, SSD 256 ГБ, GPS и LTE, зарядное устройство, батарея, стилус. "
        "S/N RK67D4895X."
    )

    pdf.kv_table(
        [
            ("Роль в проекте", "Рабочая станция управления проектом"),
            ("Марка, модель", "Getac K120"),
            ("Серийный номер", "RK67D4895X"),
            ("Память / диск (ДКП)", "16 ГБ · SSD 256 ГБ"),
            ("Связь (ДКП)", "LTE + GPS, Wi-Fi, Bluetooth"),
            ("Экран (линейка K120)", "12,5″ FHD, до 1200 нит"),
            ("Защита", "MIL-STD-810H, IP66, падение до 1,8 м"),
            ("Температура работы", "от −29 °C до +63 °C (класс изделия)"),
            ("Питание", "две батареи с горячей заменой"),
            ("ОС", "Windows — обязательна для СБИС и админки"),
            ("Документ покупки", "ДКП № 1 + акт + перевод Т-Банк 42 000 ₽"),
        ]
    )

    pdf.h2("3. Почему именно защищённый Getac, а не обычный ноутбук")
    pdf.body(
        "Для СБИС, сайтов и серверов формально хватило бы любого Windows-ПК. "
        "Обычный офисный ноутбук в условиях проекта не держит работу:"
    )
    pdf.kv_table(
        [
            (
                "Связь",
                "Домашний интернет в деревне нестабилен (в т.ч. из-за РЭБ). "
                "LTE в самом устройстве — единственный гарантированный канал "
                "до серверов, СБИС и комиссии.",
            ),
            (
                "Нет стационарного офиса",
                "Компьютер ездит: дом, объекты, МФЦ, банк. Обычный корпус "
                "не переживает дорогу, пыль, мороз, случайный удар.",
            ),
            (
                "Автономность",
                "Две батареи с заменой на ходу. Отчёт в СБИС и починка сайта не ждут розетки.",
            ),
            (
                "Полноценный Windows",
                "СБИС, КриптоПро / носитель КЭП, удалённый доступ к серверу, "
                "браузер с инструментами разработчика для ремонта сайта — "
                "это ПК, не смартфон.",
            ),
            (
                "Смартфон / планшет",
                "Не ставится рабочий контур СБИС+КЭП, неудобно чинить сайт "
                "и админить сервер. Как единственное рабочее место — непригоден.",
            ),
        ]
    )
    pdf.body(
        "Для комиссии: это рабочий компьютер под IT-контур проекта "
        "(платформа, бот, сайт, удалённое управление, отчётность), "
        "а не личный бытовой ноутбук."
    )

    pdf.h2("4. Варианты модернизации под внутренний контур")
    pdf.body(
        "На станцию не ставим сервер проекта (Odoo, бот, нейросеть, Docker). "
        "Сервер остаётся на VDS. K120 — рабочее место, с которого этим "
        "контуром управляют."
    )

    pdf.bold_body("Вариант А. Базовая настройка (без доп. закупок)")
    pdf.body(
        "Обновление Windows, шифрование диска, отдельная учётка только для "
        "проекта. Браузеры с закладками: админки сайтов, Odoo, панели VDS, "
        "Telegram. Клиент СБИС + рабочее место электронной подписи. "
        "SSH / удалённый доступ к серверу. Каталоги: договоры, закупки, "
        "отчётность, бэкапы конфигов. VPN или защищённый канал до VDS. "
        "Срок: 1–2 дня. Затраты: 0 ₽ сверх уже купленного комплекта."
    )

    pdf.bold_body("Вариант Б. Контур управления (рекомендуемый)")
    pdf.body("Всё из А, плюс то, без чего внутреннее управление рвётся в дороге:")
    pdf.bullet(
        "СБИС + КЭП на этой машине",
        "основное место сдачи отчётности ИП. Носитель подписи хранится "
        "отдельно, на станцию ставится только ПО.",
    )
    pdf.bullet(
        "LTE как основной канал",
        "SIM, проверка что админки и СБИС открываются без домашнего Wi-Fi.",
    )
    pdf.bullet(
        "Вторая батарея / автозарядка",
        "день между объектами, МФЦ и домом без поиска розетки.",
    )
    pdf.bullet(
        "Ремонт сайтов",
        "инструменты разработчика, доступ к CMS/Odoo website, чек-листы "
        "после правок (главная, магазин, формы).",
    )
    pdf.bullet(
        "Регламент серверов и ботов",
        "короткий список: здоровье контейнеров, логи бота, бэкап БД, "
        "что делать если сайт 502. Всё с этой станции, по одной инструкции.",
    )
    pdf.body("Срок: до 2 недель. Это рабочий контур ведения проекта и отчётности.")

    pdf.bold_body("Вариант В. Расширенный")
    pdf.body(
        "Док-станция дома: внешний монитор, ночной бэкап SSD на внешний диск. "
        "Запасной SSD — сдать архив сезона, не отдавая сам компьютер. "
        "Отдельный профиль «только СБИС» и профиль «только серверы». "
        "Имеет смысл при росте числа площадок и отчётных периодов."
    )

    pdf.h2("5. Что принимаем к исполнению")
    pdf.body(
        "К исполнению — вариант Б, старт сразу с варианта А на уже купленном "
        "железе. Вариант В не обязателен для текущего отчёта по закупке."
    )
    pdf.body(
        "Итог: Getac K120 используется как защищённая рабочая станция "
        "управления проектом: инфраструктура, сайты, боты, СБИС."
    )

    pdf.ln(6)
    pdf.set_font("dj", "B", 10)
    pdf.cell(0, 6, "Составил / ответственный:")
    pdf.ln(10)
    pdf.set_font("dj", "", 9.5)
    y = pdf.get_y()
    pdf.cell(0, 6, "ИП Гудков Иван Григорьевич  /_________________/")
    if _SIG.exists():
        pdf.image(str(_SIG), x=118, y=y - 10, w=34)
    pdf.ln(12)
    pdf.set_font("dj", "", 8.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        0,
        4.5,
        "Приложения: ДКП № 1 от 26.04.2025, акт приёма-передачи, "
        "квитанция Т-Банк № 1-23-658-334-285 на 42 000 ₽. "
        "Класс защиты K120 — спецификация Getac. Конфигурация экземпляра — "
        "по ДКП (16/256, GPS, LTE).",
    )

    _OUT_A.parent.mkdir(parents=True, exist_ok=True)
    _OUT_B.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(_OUT_A))
    pdf.output(str(_OUT_B))
    print(f"OK {_OUT_A}")
    print(f"OK {_OUT_B}")


if __name__ == "__main__":
    build()
