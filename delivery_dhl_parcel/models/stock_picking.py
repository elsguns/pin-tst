from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dhl_parcel_line_ids = fields.One2many(
        "dhl.parcel.line", "picking_id", string="DHL Parcels")
    dhl_is_dhlparcel = fields.Boolean(
        compute="_compute_dhl_is_dhlparcel")

    @api.depends("carrier_id", "carrier_id.delivery_type")
    def _compute_dhl_is_dhlparcel(self):
        for picking in self:
            picking.dhl_is_dhlparcel = (
                picking.carrier_id.delivery_type == "dhlparcel")
