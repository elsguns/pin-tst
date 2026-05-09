from odoo import api, models, fields, _
from odoo.exceptions import ValidationError
import requests
import logging
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    webhook_url = fields.Char(string="Webhook URL", config_parameter='dhl_ecommerce.webhook_url')
    trigger_type = fields.Selection([
        ('validate_delivery', 'Validating a delivery order'),
        ('new_stock_pick', 'A new stock pick is created'),
        ('new_sale_order', 'A sale order is created'),
    ], default="validate_delivery", required=True, string="Trigger Type", config_parameter="dhl_ecommerce.trigger_type", help="Determine when the webhook should be triggered.")

    @api.onchange('webhook_url')
    def _onchange_webhook_url(self):
        old_webhook_url = self.env['ir.config_parameter'].get_param('dhl_ecommerce.webhook_url')
        if (not self.webhook_url or self.webhook_url == old_webhook_url):
            return

        # TODO: improve validation so that no arbitray urls can be called
        # validate_webhook_url(self.webhook_url)

def validate_webhook_url(webhook_url):
    try:
        validation_url = webhook_url + '/validate'
        _logger.info("Validating webhook URL: %s", validation_url)
        response = requests.get(validation_url, timeout=5)
        _logger.info("Webhook URL validation response: %s", response.text)
        response.raise_for_status()
    except requests.RequestException as e:
        _logger.error("Error validating webhook URL: %s", e)
        userErrorMsg = _("The webhook URL is invalid. Please enter a valid URL.")
        raise UserError(userErrorMsg)
