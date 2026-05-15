from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_partner_balance = fields.Float(
        string='Баланс партнёра (руб.)',
        digits=(10, 2),
        default=0.0,
    )
