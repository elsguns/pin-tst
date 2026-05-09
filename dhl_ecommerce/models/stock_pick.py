from odoo import api, models, fields
from odoo.addons.dhl_ecommerce.models.draft_service import _create_draft_shipment
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    dhl_track_trace_number = fields.Text(
        string="Track and Trace",
        readonly=True,
        copy=True,
        tracking=True,
        default=""
    )
    webhook_sent = fields.Boolean(string="Webhook Sent", default=False)

    @api.model_create_multi
    def create(self, vals_list):
        pickings = super(StockPicking, self).create(vals_list)
        trigger_type = self.env['ir.config_parameter'].get_param('dhl_ecommerce.trigger_type')

        if trigger_type != 'new_stock_pick':
            return pickings

        self.create_draft(pickings)

        return pickings

    def button_validate(self):
        res = super(StockPicking, self).button_validate()
        trigger_type = self.env['ir.config_parameter'].get_param('dhl_ecommerce.trigger_type')

        if trigger_type != 'validate_delivery':
            return res

        self.create_draft(self)

        return res

    def create_draft(self, pickings):
        for picking in pickings:
            if picking.picking_type_id.code != 'outgoing' or picking.webhook_sent or picking.backorder_id:
                continue

            sale_order = self.env['sale.order'].search([('name', '=', picking.origin)], limit=1)
            reference = sale_order.name if sale_order.name else picking.name

            try:
                _create_draft_shipment(self, picking, reference)
                picking.webhook_sent = True
            except Exception as e:
                error_msg = "Error sending webhook for picking %s: %s"
                _logger.error(error_msg, picking.name, e)
                post_vars = {
                    'subject': "DHL eCommerce webhook",
                    'body': "Error sending webhook for picking {0}. Received error: {1}".format(picking.name, e),
                    'partner_ids': []
                }

                picking.message_post(message_type="notification", **post_vars)
