from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dhl_is_dhlparcel = fields.Boolean(
        compute="_compute_dhl_is_dhlparcel")
    dhl_carrier_parcel_type = fields.Selection(
        related="carrier_id.dhlparcel_parcel_type")
    dhl_partner_is_company = fields.Boolean(
        related="partner_id.is_company",
        help="Drives the recipient-aware parcel-type columns on the "
             "DHL Parcels lines.")
    dhl_partner_country_id = fields.Many2one(
        "res.country", related="partner_id.country_id")
    dhl_parcel_count = fields.Integer(
        string="Aantal pakketten", default=1,
        help="Aantal identieke pakketten in deze zending (multicollo). "
             "Genegeerd zodra je Put in Pack gebruikt: dan bepalen de "
             "aangemaakte packages het aantal pieces.")
    dhl_parcel_line_ids = fields.One2many(
        "dhl.parcel.line", "picking_id", string="DHL Parcels",
        help="Used only for DHL methods with parcel type 'Gemengd' (MIX): "
             "one row per parcel, type + qty + optional weight.")

    @api.depends("carrier_id", "carrier_id.delivery_type")
    def _compute_dhl_is_dhlparcel(self):
        for picking in self:
            picking.dhl_is_dhlparcel = (
                picking.carrier_id.delivery_type == "dhlparcel")
