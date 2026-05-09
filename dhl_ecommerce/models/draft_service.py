import json
import logging
import requests
import urllib.parse

_logger = logging.getLogger(__name__)

def _create_draft_shipment(self, shipment_data, reference):
    webhook_url = self.env['ir.config_parameter'].get_param('dhl_ecommerce.webhook_url')
    trigger_type = self.env['ir.config_parameter'].get_param('dhl_ecommerce.trigger_type')

    if not webhook_url:
        _logger.warning("Webhook configuration is not set.")
        return

    payload = get_payload(shipment_data, trigger_type, reference)

    response = requests.post(webhook_url, json=payload, timeout=5)
    response.raise_for_status()
    success_msg = "Webhook sent successfully for sale order %s"
    _logger.info(success_msg, reference)

    post_vars = {
        'subject': "DHL eCommerce webhook",
        'body': "Successfully sent request to create draft shipment",
        'partner_ids': []
    }
    shipment_data.message_post(message_type="notification", **post_vars)

def get_payload(shipment_data, trigger_type, reference):
    partner = shipment_data.partner_id

    if (partner.name):
        full_name = partner.name.split(' ', 1)
        first_name = full_name[0] if full_name else ''
        last_name = full_name[1] if len(full_name) > 1 else ''
    else:
        first_name = ''
        last_name = ''

    company = partner.name if partner.is_company else ''
    email = partner.email or ''
    phone_number = partner.phone or ''
    country_code = partner.country_id.code or ''
    postal_code = partner.zip or ''
    city = partner.city or ''
    street = partner.street or ''

    return {
            "triggerType": trigger_type,
            "referenceId": shipment_data.id,
            "referenceName": reference,
            "shipmentDetails": {
                "company": company,
                "firstName": first_name,
                "lastName": last_name,
                "email": email,
                "phoneNumber": phone_number,
                "countryCode": country_code,
                "postalCode": postal_code,
                "city": city,
                "street": street
            }
        }
