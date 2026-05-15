from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_partner_balance = fields.Float(
        string='Баланс партнёра (руб.)',
        digits=(10, 2),
        default=0.0,
    )
    x_telegram_id = fields.Char(
        string='Telegram ID',
        index=True,
        help='Telegram user ID для привязки бота к контакту.',
    )
    x_is_premium = fields.Boolean(
        string='Premium подписка',
        default=False,
    )
    x_premium_ends = fields.Date(
        string='Premium до',
        help='Дата окончания Premium подписки.',
    )
