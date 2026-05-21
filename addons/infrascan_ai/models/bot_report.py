from odoo import fields, models


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
