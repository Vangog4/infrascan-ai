from odoo import api, fields, models
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/{model}:generateContent?key={key}"
)

_LEADS_PROJECT_ID = 1  # проект "Выезд"


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_telegram_id = fields.Char(
        string='Telegram ID инженера',
        help='Telegram user ID исполнителя. Задача показывается только ему в боте.',
    )

    def _get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    # ── Уведомление в Telegram при создании лида ────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if (record.project_id.id == _LEADS_PROJECT_ID
                    and record.name.startswith('[Лид]')):
                record._notify_telegram_lead()
        return records

    def _notify_telegram_lead(self):
        token = self._get_param('infrascan_ai.telegram_bot_token')
        admin_ids_raw = self._get_param('infrascan_ai.telegram_admin_ids') or ''
        if not token or not admin_ids_raw:
            return

        desc = (self.description or '').replace('<br>', '\n').replace('<br/>', '\n')
        # strip any remaining html tags simply
        import re
        desc_clean = re.sub(r'<[^>]+>', '', desc).strip()

        text = (
            f"📥 <b>Новый лид с сайта!</b>\n\n"
            f"<b>{self.name}</b>\n"
            f"{desc_clean[:500]}"
        )

        for raw_id in admin_ids_raw.split(','):
            chat_id = raw_id.strip()
            if not chat_id:
                continue
            try:
                requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                    timeout=5,
                )
            except Exception as e:
                _logger.warning("Telegram notify failed for chat_id=%s: %s", chat_id, e)

    # ── Анализ термограммы через Gemini ─────────────────────────────────────

    def action_analyze_thermal_image(self):
        api_key = self._get_param('infrascan_ai.gemini_api_key')
        if not api_key or api_key == 'REPLACE_WITH_YOUR_GEMINI_API_KEY':
            raise UserError(
                "Gemini API key не настроен. "
                "Откройте Настройки → Технические → Системные параметры "
                "и задайте 'infrascan_ai.gemini_api_key'."
            )

        model = self._get_param('infrascan_ai.gemini_model') or 'gemini-2.0-flash'
        url = _GEMINI_URL.format(model=model, key=api_key)

        prompt = (
            "Ты — эксперт по тепловизионной и строительной диагностике зданий ИнфраСкан.\n"
            "Проанализируй термограмму и дай заключение в формате ниже.\n\n"
            "Объект: [тип — окно / стена / электрощит / фасад / кровля / другое]\n\n"
            "🌡 Температурная картина\n"
            "• [наблюдение; если видны температуры — указывай °C]\n"
            "• [наблюдение 2]\n\n"
            "⚠️ Выявленные проблемы\n"
            "• [проблема или риск]\n"
            "• [проблема 2 если есть]\n\n"
            "📊 Уровень риска: [НИЗКИЙ / СРЕДНИЙ / ВЫСОКИЙ / КРИТИЧЕСКИЙ]\n\n"
            "💡 Рекомендация: [1–2 предложения — что сделать и примерная стоимость устранения]\n\n"
            "Пиши по-русски, кратко и конкретно — как эксперт на осмотре."
        )

        for task in self:
            _logger.info("InfraScan AI: анализ задачи %s", task.id)
            task.message_post(body="⚙️ <i>Кибер-прораб: Анализирую снимки...</i>")

            attachment = self.env['ir.attachment'].search([
                ('res_model', '=', 'project.task'),
                ('res_id', '=', task.id),
                ('mimetype', 'ilike', 'image'),
            ], order='create_date desc', limit=1)

            if not attachment:
                task.message_post(body="⚠️ Фото не найдено. Прикрепите термограмму.")
                continue

            raw = attachment.datas
            if not raw:
                task.message_post(body="⚠️ Файл вложения пустой.")
                continue

            image_data = raw.decode('ascii')

            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {
                            "mime_type": attachment.mimetype,
                            "data": image_data,
                        }},
                    ]
                }]
            }

            try:
                response = requests.post(url, json=payload, timeout=30)
            except requests.exceptions.Timeout:
                _logger.warning("InfraScan AI: таймаут запроса для задачи %s", task.id)
                task.message_post(body="⚠️ Gemini не ответил за 30 сек. Попробуйте снова.")
                continue
            except requests.exceptions.RequestException as e:
                _logger.exception("InfraScan AI: сетевая ошибка для задачи %s", task.id)
                task.message_post(body=f"❌ Сетевая ошибка: {e}")
                continue

            if response.status_code != 200:
                snippet = response.text[:300]
                _logger.error(
                    "InfraScan AI: HTTP %s от Gemini для задачи %s: %s",
                    response.status_code, task.id, snippet,
                )
                task.message_post(
                    body=f"❌ Ошибка Gemini HTTP {response.status_code}:<br/><code>{snippet}</code>"
                )
                continue

            try:
                data = response.json()
                answer = data['candidates'][0]['content']['parts'][0]['text']
                task.message_post(body=f"🤖 <b>Вердикт:</b><br/>{answer}")
            except (KeyError, IndexError, ValueError):
                _logger.error("InfraScan AI: неожиданный формат ответа: %s", response.text[:500])
                task.message_post(body="⚠️ Gemini ответил, но формат неожиданный. Смотрите логи.")
        return True
