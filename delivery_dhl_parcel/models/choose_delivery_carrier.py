from odoo import fields, models


class ChooseDeliveryCarrier(models.TransientModel):
    _inherit = "choose.delivery.carrier"

    # Loaded so the view domain on carrier_id can branch on the partner
    # being a company without relying on partner_id.is_company dot-notation
    # (which the view evaluator doesn't always dereference correctly).
    dhl_partner_is_company = fields.Boolean(
        related="order_id.partner_id.is_company")
