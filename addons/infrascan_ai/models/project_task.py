import logging
import re
from datetime import date, datetime, timedelta

import requests
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta"
    "/models/{model}:generateContent?key={key}"
)
_TG_URL = "https://api.telegram.org/bot{token}/sendMessage"


class ProjectTask(models.Model):
    _inherit = 'project.task'

    x_telegram_id = fields.Char(
        string='Telegram ID инженера',
        help='Telegram user ID исполнителя. Задача показывается только ему в боте.',
    )

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _get_param(self, key):
        return self.env['ir.config_parameter'].sudo().get_param(key)

    def _leads_project_id(self):
        return int(self._get_param('infrascan_ai.leads_project_id') or '1')

    def _get_admin_ids(self):
        raw = self._get_param('infrascan_ai.telegram_admin_ids') or ''
        return [c.strip() for c in raw.split(',') if c.strip()]

    def _send_telegram(self, chat_ids, text, parse_mode='HTML'):
        token = self._get_param('infrascan_ai.telegram_bot_token')
        if not token or not chat_ids:
            return
        if isinstance(chat_ids, str):
            chat_ids = [chat_ids]
        url = _TG_URL.format(token=token)
        for chat_id in chat_ids:
            try:
                requests.post(
                    url,
                    json={'chat_id': chat_id, 'text': text, 'parse_mode': parse_mode},
                    timeout=5,
                )
            except Exception as e:
                _logger.warning("Telegram notify failed for %s: %s", chat_id, e)

    def _gemini_generate(self, prompt, max_tokens=200):
        api_key = self._get_param('infrascan_ai.gemini_api_key')
        model = self._get_param('infrascan_ai.gemini_model') or 'gemini-2.5-flash'
        if not api_key or api_key == 'REPLACE_WITH_YOUR_GEMINI_API_KEY':
            return None
        url = _GEMINI_URL.format(model=model, key=api_key)
        try:
            resp = requests.post(url, json={
                'contents': [{'parts': [{'text': prompt}]}],
                'generationConfig': {'maxOutputTokens': max_tokens, 'temperature': 0.7},
            }, timeout=15)
            if resp.status_code == 200:
                return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        except Exception as e:
            _logger.warning("Gemini generate failed: %s", e)
        return None

    # ── Auto-notifications on write ──────────────────────────────────────────

    def write(self, vals):
        old_tg = {t.id: t.x_telegram_id for t in self}
        old_stage = {t.id: (t.stage_id.id, t.stage_id.name) for t in self}
        result = super().write(vals)

        if 'x_telegram_id' in vals and vals.get('x_telegram_id'):
            for task in self:
                if task.x_telegram_id != old_tg.get(task.id):
                    task._notify_engineer_assigned()

        if 'stage_id' in vals:
            done_kw = {'выполнена', 'выполнено', 'done', 'завершена', 'закрыта'}
            for task in self:
                new_stage_name = task.stage_id.name.lower().strip()
                _, old_name = old_stage.get(task.id, (None, ''))
                if task.stage_id.id != old_stage.get(task.id, (None,))[0]:
                    if any(kw in new_stage_name for kw in done_kw):
                        task._notify_admin_task_done()
                    elif task.x_telegram_id:
                        task._notify_engineer_stage_change(old_name, task.stage_id.name)

        return result

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        proj_id = self._leads_project_id()
        for record in records:
            if record.project_id.id == proj_id and record.name.startswith('[Лид]'):
                record._notify_telegram_lead()
            elif record.x_telegram_id and record.project_id.id == proj_id:
                record._notify_engineer_assigned()
        return records

    # ── Notification templates ────────────────────────────────────────────────

    def _notify_engineer_assigned(self):
        if not self.x_telegram_id:
            return
        deadline = (
            self.date_deadline.strftime('%d.%m.%Y') if self.date_deadline else 'не указана'
        )
        desc_clean = re.sub(r'<[^>]+>', '', self.description or '').strip()
        desc_block = f"\n\n📝 {desc_clean[:300]}" if desc_clean else ''
        text = (
            f"📋 <b>Вам назначен выезд!</b>\n\n"
            f"🏗 <b>Объект:</b> {self.name}\n"
            f"📅 <b>Дата:</b> {deadline}\n"
            f"📁 <b>Проект:</b> {self.project_id.name}"
            f"{desc_block}\n\n"
            f"<i>Используйте бота для сдачи отчёта: /start</i>"
        )
        self._send_telegram([self.x_telegram_id], text)
        _logger.info("Notified engineer %s about task %d", self.x_telegram_id, self.id)

    def _notify_engineer_stage_change(self, old_stage, new_stage):
        if not self.x_telegram_id:
            return
        text = (
            f"🔄 <b>Статус задачи изменён</b>\n\n"
            f"🏗 {self.name}\n"
            f"{old_stage} → <b>{new_stage}</b>"
        )
        self._send_telegram([self.x_telegram_id], text)

    def _notify_admin_task_done(self):
        admin_ids = self._get_admin_ids()
        if not admin_ids:
            return
        engineer = self.x_telegram_id or '—'
        now_str = datetime.now().strftime('%d.%m.%Y %H:%M')
        text = (
            f"✅ <b>Выезд выполнен!</b>\n\n"
            f"🏗 <b>Объект:</b> {self.name}\n"
            f"👷 <b>Инженер TG:</b> <code>{engineer}</code>\n"
            f"🕐 <b>Закрыта:</b> {now_str}"
        )
        self._send_telegram(admin_ids, text)

    def _notify_telegram_lead(self):
        admin_ids = self._get_admin_ids()
        token = self._get_param('infrascan_ai.telegram_bot_token')
        if not token or not admin_ids:
            return

        desc_clean = re.sub(r'<[^>]+>', '', (self.description or '')).strip()

        # Gemini: оценка качества лида
        quality_line = ''
        if desc_clean:
            prompt = (
                f"Ты — менеджер строительной компании. Тебе пришёл новый лид:\n{desc_clean[:500]}\n\n"
                f"Оцени в одном предложении (до 12 слов): насколько перспективен этот лид "
                f"и какое первое действие рекомендуешь? Пиши по-русски, без кавычек."
            )
            ai_tip = self._gemini_generate(prompt, max_tokens=80)
            if ai_tip:
                quality_line = f"\n\n💡 <i>ИИ: {ai_tip}</i>"

        text = (
            f"📥 <b>Новый лид!</b>\n\n"
            f"<b>{self.name}</b>\n"
            f"{desc_clean[:400]}"
            f"{quality_line}"
        )
        self._send_telegram(admin_ids, text)

    # ── Manual action button ─────────────────────────────────────────────────

    def action_notify_engineer(self):
        for task in self:
            if not task.x_telegram_id:
                raise UserError(
                    f"У задачи «{task.name}» не заполнен Telegram ID инженера."
                )
            task._notify_engineer_assigned()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Уведомление отправлено',
                'message': f'Инженер (TG: {self.x_telegram_id}) получил задачу в Telegram.',
                'type': 'success',
                'sticky': False,
            },
        }

    # ── Gemini thermal analysis (existing, unchanged) ────────────────────────

    def action_analyze_thermal_image(self):
        api_key = self._get_param('infrascan_ai.gemini_api_key')
        if not api_key or api_key == 'REPLACE_WITH_YOUR_GEMINI_API_KEY':
            raise UserError(
                "Gemini API key не настроен. "
                "Откройте Настройки → Технические → Системные параметры "
                "и задайте 'infrascan_ai.gemini_api_key'."
            )

        model = self._get_param('infrascan_ai.gemini_model') or 'gemini-2.5-flash'
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
                task.message_post(body="⚠️ Gemini не ответил за 30 сек. Попробуйте снова.")
                continue
            except requests.exceptions.RequestException as e:
                task.message_post(body=f"❌ Сетевая ошибка: {e}")
                continue

            if response.status_code != 200:
                snippet = response.text[:300]
                task.message_post(
                    body=f"❌ Ошибка Gemini HTTP {response.status_code}:<br/><code>{snippet}</code>"
                )
                continue

            try:
                data = response.json()
                answer = data['candidates'][0]['content']['parts'][0]['text']
                task.message_post(body=f"🤖 <b>Вердикт Кибер-прораба:</b><br/>{answer}")
            except (KeyError, IndexError, ValueError):
                task.message_post(body="⚠️ Gemini ответил, но формат неожиданный. Смотрите логи.")
        return True

    # ── Cron: morning digest ─────────────────────────────────────────────────

    @api.model
    def morning_digest_cron(self):
        proj_id = self._leads_project_id()
        today = date.today().isoformat()

        tasks = self.search([
            ['project_id', '=', proj_id],
            '|', ['date_deadline', '=', today], ['date_deadline', '=', False],
            ['name', 'not ilike', '[Лид]'],
        ])

        # Group by engineer TG ID
        by_engineer = {}
        unassigned = []
        for t in tasks:
            tg = (t.x_telegram_id or '').strip()
            if tg:
                by_engineer.setdefault(tg, []).append(t)
            else:
                unassigned.append(t)

        # Send personal digest to each engineer
        for tg_id, eng_tasks in by_engineer.items():
            lines = []
            for i, t in enumerate(eng_tasks, 1):
                dl = t.date_deadline.strftime('%d.%m') if t.date_deadline else '—'
                stage = t.stage_id.name if t.stage_id else 'новая'
                lines.append(f"{i}. <b>{t.name}</b>\n   📅 {dl}  ·  {stage}")

            count = len(eng_tasks)
            text = (
                f"🌅 <b>Доброе утро!</b> Ваш план на {date.today().strftime('%d.%m.%Y')}:\n\n"
                + "\n\n".join(lines)
                + f"\n\n📊 Итого: <b>{count}</b> {'выезд' if count == 1 else 'выездов'}\n"
                f"<i>Отчёт сдаётся через бота: /start</i>"
            )
            self._send_telegram([tg_id], text)
            _logger.info("Morning digest sent to engineer %s (%d tasks)", tg_id, count)

        # Notify admin about unassigned tasks
        if unassigned:
            admin_ids = self._get_admin_ids()
            lines = [f"• {t.name} ({t.date_deadline or 'без даты'})" for t in unassigned[:10]]
            text = (
                f"⚠️ <b>Задачи без инженера на {date.today().strftime('%d.%m')}:</b>\n\n"
                + "\n".join(lines)
                + "\n\n<i>Назначьте исполнителей в Odoo.</i>"
            )
            self._send_telegram(admin_ids, text)

    # ── Cron: evening summary ────────────────────────────────────────────────

    @api.model
    def evening_summary_cron(self):
        admin_ids = self._get_admin_ids()
        if not admin_ids:
            return

        proj_id = self._leads_project_id()
        today_start = datetime.combine(date.today(), datetime.min.time())

        all_tasks = self.search([
            ['project_id', '=', proj_id],
            ['name', 'not ilike', '[Лид]'],
        ])
        leads_today = self.search([
            ['project_id', '=', proj_id],
            ['name', 'ilike', '[Лид]'],
            ['create_date', '>=', today_start.isoformat()],
        ])

        done_kw = {'выполнена', 'выполнено', 'done', 'завершена', 'закрыта', 'архив'}
        done = [t for t in all_tasks if any(kw in t.stage_id.name.lower() for kw in done_kw)]
        in_progress = [t for t in all_tasks if t not in done]
        overdue = [
            t for t in in_progress
            if t.date_deadline and t.date_deadline < date.today()
        ]
        unassigned = [t for t in in_progress if not t.x_telegram_id]

        # Gemini: daily insight
        insight = self._gemini_evening_insight(
            done=len(done),
            in_progress=len(in_progress),
            overdue=len(overdue),
            leads=len(leads_today),
        )

        text = (
            f"📊 <b>Итог дня — {date.today().strftime('%d.%m.%Y')}</b>\n\n"
            f"✅ Выполнено выездов: <b>{len(done)}</b>\n"
            f"🔄 В работе: <b>{len(in_progress)}</b>\n"
            f"📋 Новых лидов сегодня: <b>{len(leads_today)}</b>\n"
        )

        if overdue:
            text += f"\n⚠️ <b>Просрочено ({len(overdue)}):</b>\n"
            for t in overdue[:5]:
                dl = t.date_deadline.strftime('%d.%m') if t.date_deadline else '—'
                text += f"• {t.name} ({dl})\n"

        if unassigned:
            text += f"\n👤 <b>Без инженера: {len(unassigned)}</b> — требуют назначения\n"

        if insight:
            text += f"\n💡 <i>{insight}</i>"

        self._send_telegram(admin_ids, text)
        _logger.info("Evening summary sent to %d admins", len(admin_ids))

    def _gemini_evening_insight(self, done, in_progress, overdue, leads):
        if done + in_progress + leads == 0:
            return None
        prompt = (
            f"Ты — аналитик строительной компании InfraScan. "
            f"Итоги рабочего дня: выполнено {done} выездов, в работе {in_progress}, "
            f"просрочено {overdue}, новых заявок от клиентов {leads}. "
            f"Напиши одно мотивирующее аналитическое предложение на русском (до 20 слов). "
            f"Если есть просрочки — мягко отметь. Без кавычек, без эмодзи."
        )
        return self._gemini_generate(prompt, max_tokens=60)

    # ── Cron: lead follow-up ─────────────────────────────────────────────────

    @api.model
    def lead_followup_cron(self):
        admin_ids = self._get_admin_ids()
        if not admin_ids:
            return

        proj_id = self._leads_project_id()
        threshold = datetime.now() - timedelta(hours=2)
        done_kw = {'выполнена', 'выполнено', 'done', 'завершена', 'закрыта', 'архив'}

        stale_leads = self.search([
            ['project_id', '=', proj_id],
            ['name', 'ilike', '[Лид]'],
            ['create_date', '<=', threshold.isoformat()],
        ])
        # Filter out leads already in done stage
        stale_leads = [
            lead for lead in stale_leads
            if not any(kw in (lead.stage_id.name or '').lower() for kw in done_kw)
        ]

        if not stale_leads:
            return

        lines = []
        for lead in stale_leads[:8]:
            age_h = int((datetime.now() - lead.create_date).total_seconds() // 3600)
            desc_clean = re.sub(r'<[^>]+>', '', lead.description or '').strip()
            phone_match = re.search(r'\+?[\d\s\-]{10,}', desc_clean)
            phone = phone_match.group().strip() if phone_match else '—'
            lines.append(f"• {lead.name} | 📞 {phone} | ⏱ {age_h}ч без ответа")

        text = (
            f"⏰ <b>Необработанные лиды ({len(stale_leads)})</b>\n\n"
            + "\n".join(lines)
            + "\n\n<i>Откройте Odoo CRM для обработки.</i>"
        )
        self._send_telegram(admin_ids, text)
        _logger.info("Lead follow-up: notified %d stale leads", len(stale_leads))
