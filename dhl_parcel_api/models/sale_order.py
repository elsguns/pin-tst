from odoo import _, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    dhl_parcel_tracker_code = fields.Char(
        string="DHL Tracker",
        copy=False,
        readonly=True,
        tracking=True,
    )
    dhl_parcel_shipment_id = fields.Char(
        string="DHL Shipment ID",
        copy=False,
        readonly=True,
        help="Client-side UUID we sent to DHL as shipmentId — kept for "
             "idempotent retries and label re-fetching.",
    )

    def action_open_dhl_parcel_wizard(self):
        self.ensure_one()
        return {
            "name": _("Create DHL Parcel shipment"),
            "type": "ir.actions.act_window",
            "res_model": "dhl.shipment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_sale_order_id": self.id},
        }
