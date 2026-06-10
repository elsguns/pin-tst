from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dhl_is_dhlparcel = fields.Boolean(
        compute="_compute_dhl_is_dhlparcel")
    dhl_parcel_count = fields.Integer(
        string="Aantal pakketten", default=1,
        help="Aantal identieke pakketten in deze zending (multicollo). "
             "Genegeerd zodra je Put in Pack gebruikt: dan bepalen de "
             "aangemaakte packages het aantal pieces.")

    @api.depends("carrier_id", "carrier_id.delivery_type")
    def _compute_dhl_is_dhlparcel(self):
        for picking in self:
            picking.dhl_is_dhlparcel = (
                picking.carrier_id.delivery_type == "dhlparcel")
