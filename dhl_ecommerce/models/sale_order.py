from odoo import api, models, fields
from odoo.addons.dhl_ecommerce.models.draft_service import _create_draft_shipment
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    dhl_track_trace_number = fields.Text(string="Track and Trace", readonly=True, copy=True, tracking=True, default="")

    @api.model_create_multi
    def create(self, vals_list):
        sale_orders = super().create(vals_list)
        trigger_type = self.env['ir.config_parameter'].sudo().get_param('dhl_ecommerce.trigger_type')

        if trigger_type == 'new_sale_order':
            for sale_order in sale_orders:
                try:
                    _create_draft_shipment(self, sale_order, sale_order.name)
                except Exception as e:
                    _logger.error("Error sending webhook for sale order %s: %s", sale_order.name, e)
                    sale_order.message_post(
                        subject="DHL eCommerce webhook",
                        body="Error sending webhook for sale order {0}. Received error: {1}".format(sale_order.name, e),
                        message_type="notification",
                        partner_ids=[],
                    )

        return sale_orders
