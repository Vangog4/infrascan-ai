import logging
from datetime import datetime, timedelta

import requests
from odoo import fields, models

_logger = logging.getLogger(__name__)
_TG_URL = "https://api.telegram.org/bot{token}/sendMessage"


class InfraScanBotReport(models.Model):
    _name = 'infrascan.bot.report'
    _description = 'InfraScan Bot Analysis Report'
    _order = 'create_date desc'

    client_tg_id = fields.Char(string='Client Telegram ID', index=True)
    object_type = fields.Char(string='Object Type')
    risk_level = fields.Selection([
        ('LOW', 'LOW'), ('MEDIUM', 'MEDIUM'), ('HIGH', 'HIGH'), ('CRITICAL', 'CRITICAL'),
    ], string='Risk Level')
    risk_score = fields.Float(string='Risk Score')
    verdict = fields.Text(string='Free Verdict')
    is_premium = fields.Boolean(string='Premium Report', default=False)

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def _send_telegram(self, chat_id, text):
        token = self._get_param('infrascan_ai.telegram_bot_token')
        if not token or not chat_id:
            return
        try:
            requests.post(
                _TG_URL.format(token=token),
                json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
                timeout=5,
            )
        except Exception as e:
            _logger.warning("Telegram monthly digest failed for %s: %s", chat_id, e)

    # ── Monthly B2B Digest ────────────────────────────────────────────────────

    def monthly_digest_cron(self):
        since = datetime.utcnow() - timedelta(days=30)
        reports = self.search([('create_date', '>=', since.strftime('%Y-%m-%d %H:%M:%S'))])
        if not reports:
            return

        by_user = {}
        for r in reports:
            by_user.setdefault(r.client_tg_id, []).append(r)

        for tg_id, user_reports in by_user.items():
            if not tg_id:
                continue
            total = len(user_reports)
            risk_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'CRITICAL': 0}
            for r in user_reports:
                if r.risk_level:
                    risk_counts[r.risk_level] += 1
            scores = [r.risk_score for r in user_reports if r.risk_score]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
            month_name = since.strftime('%B %Y')

            text = (
                f"📊 <b>Ваш отчёт InfraScan за {month_name}</b>\n\n"
                f"Выполнено анализов: <b>{total}</b>\n"
                f"Средний уровень риска: <b>{avg_score}%</b>\n\n"
                f"Распределение рисков:\n"
                f"  🟢 Низкий: {risk_counts['LOW']}\n"
                f"  🟡 Средний: {risk_counts['MEDIUM']}\n"
                f"  🔴 Высокий: {risk_counts['HIGH']}\n"
                f"  🚨 Критический: {risk_counts['CRITICAL']}\n\n"
                f"<i>Для углублённого анализа отправьте новое фото или закажите выезд инженера.</i>"
            )
            self._send_telegram(tg_id, text)
