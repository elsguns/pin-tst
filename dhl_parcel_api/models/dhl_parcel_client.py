import logging
import uuid

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

API_BASE = "https://api-gw.dhlparcel.nl"
AUTH_PATH = "/authenticate/api-key"
SHIPMENTS_PATH = "/shipments"
LABEL_PATH = "/labels/{shipment_id}"

REQUEST_TIMEOUT = 30


class DhlParcelClient(models.AbstractModel):
    """Thin wrapper around the DHL Parcel API. Stateless: every public call
    authenticates fresh and re-uses the token for any follow-up requests
    within the same call. We deliberately do not cache tokens across calls
    in v1 — simpler, and the ~15min token lifetime gives nothing useful
    to cache for the button-driven, low-volume flow."""

    _name = "dhl.parcel.client"
    _description = "DHL Parcel API client"

    def _get_credentials(self):
        get_param = self.env["ir.config_parameter"].sudo().get_param
        user_id = get_param("dhl_parcel_api.user_id")
        key = get_param("dhl_parcel_api.api_key")
        account_id = get_param("dhl_parcel_api.account_id")
        if not (user_id and key and account_id):
            raise UserError(_(
                "DHL Parcel API credentials are not configured. "
                "Go to Settings > DHL Parcel API (left sidebar) and fill in "
                "User ID, API Key and Account ID."
            ))
        return user_id, key, account_id

    def _authenticate(self):
        user_id, key, _account_id = self._get_credentials()
        try:
            response = requests.post(
                API_BASE + AUTH_PATH,
                json={"userId": user_id, "key": key},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise UserError(_("Could not reach DHL Parcel API: %s") % exc) from exc

        if response.status_code != 200:
            raise UserError(_(
                "DHL Parcel authentication failed (HTTP %(code)s): %(body)s",
                code=response.status_code,
                body=response.text,
            ))
        token = response.json().get("accessToken")
        if not token:
            raise UserError(_("DHL Parcel authentication returned no accessToken."))
        return token

    def create_shipment(self, payload):
        """POST /shipments. Returns the parsed JSON response (contains
        shipmentId, trackerCode, pieces, …). Raises UserError on any
        non-success."""
        token = self._authenticate()
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            response = requests.post(
                API_BASE + SHIPMENTS_PATH,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise UserError(_("DHL Parcel API call failed: %s") % exc) from exc

        if response.status_code not in (200, 201):
            _logger.warning(
                "DHL Parcel POST /shipments failed: %s — %s",
                response.status_code, response.text,
            )
            raise UserError(_(
                "DHL Parcel rejected the shipment (HTTP %(code)s):\n%(body)s",
                code=response.status_code,
                body=response.text,
            ))
        return token, response.json()

    def fetch_label_pdf(self, shipment_id, token=None):
        """GET /labels/{id} with Accept: application/pdf. Returns raw bytes.
        Re-uses `token` if provided, otherwise authenticates fresh."""
        if not token:
            token = self._authenticate()
        headers = {
            "Authorization": "Bearer " + token,
            "Accept": "application/pdf",
        }
        url = API_BASE + LABEL_PATH.format(shipment_id=shipment_id)
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not fetch DHL label PDF: %s") % exc) from exc

        if response.status_code != 200:
            raise UserError(_(
                "DHL Parcel label fetch failed (HTTP %(code)s): %(body)s",
                code=response.status_code,
                body=response.text[:500],
            ))
        return response.content

    def new_shipment_uuid(self):
        return str(uuid.uuid4())
