"""Before/After comparison for thermal analysis results."""

_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
_RISK_LABEL = {"LOW": "🟢 LOW", "MEDIUM": "🟡 MEDIUM", "HIGH": "🟠 HIGH", "CRITICAL": "🔴 CRITICAL"}


def format_comparison(old: dict, new: dict, locale: str = "ru") -> str:
    old_risk = old.get("risk_level", "")
    new_risk = new.get("risk_level", "")
    old_score = float(old.get("risk_score", 0))
    new_score = float(new.get("risk_score", 0))

    old_ord = _RISK_ORDER.get(old_risk, -1)
    new_ord = _RISK_ORDER.get(new_risk, -1)

    if new_ord < old_ord:
        trend = "✅ Улучшение!" if locale == "ru" else "✅ Improved!"
    elif new_ord > old_ord:
        trend = "❗ Ухудшение!" if locale == "ru" else "❗ Worsened!"
    else:
        trend = "➡️ Без изменений" if locale == "ru" else "➡️ No change"

    score_delta = new_score - old_score
    delta_str = f"{score_delta:+.2f}"
    delta_icon = "📉" if score_delta < -0.05 else ("📈" if score_delta > 0.05 else "📊")

    old_label = _RISK_LABEL.get(old_risk, old_risk)
    new_label = _RISK_LABEL.get(new_risk, new_risk)

    if locale == "ru":
        return (
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>Сравнение с предыдущим анализом</b>\n\n"
            f"Было:  {old_label}  (счёт {old_score:.2f})\n"
            f"Стало: {new_label}  (счёт {new_score:.2f})\n"
            f"{delta_icon} Изменение счёта: <b>{delta_str}</b>\n\n"
            f"{trend}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
    return (
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Comparison with previous analysis</b>\n\n"
        f"Before: {old_label}  (score {old_score:.2f})\n"
        f"After:  {new_label}  (score {new_score:.2f})\n"
        f"{delta_icon} Score change: <b>{delta_str}</b>\n\n"
        f"{trend}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
