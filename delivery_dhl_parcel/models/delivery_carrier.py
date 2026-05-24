import logging
import re
import uuid

import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

API_BASE = "https://api-gw.dhlparcel.nl"
AUTH_PATH = "/authenticate/api-key"
SHIPMENTS_PATH = "/shipments"
LABEL_PATH = "/labels/%s"
TIMEOUT = 30
# Public consumer track & trace page (tracker + postcode). Provisional URL.
TRACK_URL = "https://www.dhlparcel.nl/nl/consument/traceer-uw-zending?tt=%s"


def _extract_address(partner):
    """Best-effort (street, number, addition) from an Odoo partner.

    Handles: BE convention (number in street2), default Odoo (number in
    street), and mixed (number in street, addition in street2).
    """
    street = (partner.street or "").strip()
    street2 = (partner.street2 or "").strip()
    if street2 and re.match(r"^\d", street2):
        m = re.match(r"^(\d+)\s*(.*)$", street2)
        return street, m.group(1), m.group(2).strip()
    m = re.search(r"^(.*?)\s+(\d+\w*)\s*$", street)
    if m:
        return m.group(1).strip(), m.group(2), street2
    return street, "", street2


def _split_name(name):
    parts = (name or "").strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", name or ""


class DeliveryCarrier(models.Model):
    _inherit = "delivery.carrier"

    delivery_type = fields.Selection(
        selection_add=[("dhlparcel", "DHL Parcel (Benelux)")],
        ondelete={"dhlparcel": lambda recs: recs.write(
            {"delivery_type": "fixed", "fixed_price": 0})},
    )

    # --- credentials (per carrier; multi-account ready) ---
    dhlparcel_user_id = fields.Char("DHL User ID", copy=False)
    dhlparcel_api_key = fields.Char("DHL API Key", copy=False)
    dhlparcel_account_id = fields.Char(
        "DHL Account ID", copy=False,
        help="Short DHL account number, e.g. 08500001.")

    # --- behaviour ---
    dhlparcel_pricing_mode = fields.Selection(
        [("flat", "Flat price"), ("rule", "Weight-based rules")],
        string="DHL pricing mode", default="flat",
        help="The DHL Parcel API does not return live rates, so the customer "
             "price is set here: a flat amount, or the weight/price rules on "
             "the Pricing tab.")
    dhlparcel_flat_price = fields.Float("DHL flat price", default=0.0)
    dhlparcel_default_parcel_type = fields.Selection(
        [
            ("XSMALL", "XSmall — mailbox parcel"),
            ("SMALL", "Small — regular parcel"),
            ("ENVELOPE", "Envelope"),
            ("PALLET", "Pallet"),
        ],
        string="Default parcel type", default="SMALL")
    dhlparcel_default_weight = fields.Float(
        "Default weight (kg)", default=1.0,
        help="Used when a parcel's weight is 0 (e.g. products without a weight "
             "set). DHL refuses a 0 kg shipment, so this value is sent instead.")

    # ------------------------------------------------------------------
    # API plumbing
    # ------------------------------------------------------------------
    def _dhlparcel_authenticate(self):
        self.ensure_one()
        carrier = self.sudo()
        if not (carrier.dhlparcel_user_id and carrier.dhlparcel_api_key):
            raise UserError(_(
                "DHL Parcel credentials are not set on shipping method '%s'."
            ) % self.name)
        try:
            resp = requests.post(
                API_BASE + AUTH_PATH,
                json={"userId": carrier.dhlparcel_user_id,
                      "key": carrier.dhlparcel_api_key},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise UserError(_("Could not reach DHL Parcel API: %s") % exc) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "DHL Parcel authentication failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text))
        token = resp.json().get("accessToken")
        if not token:
            raise UserError(_("DHL Parcel authentication returned no accessToken."))
        return token

    def _dhlparcel_create_shipment(self, payload, token):
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = requests.post(API_BASE + SHIPMENTS_PATH, json=payload,
                                 headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("DHL Parcel API call failed: %s") % exc) from exc
        if resp.status_code not in (200, 201):
            _logger.warning("DHL Parcel POST /shipments failed: %s — %s",
                            resp.status_code, resp.text)
            raise UserError(_(
                "DHL Parcel rejected the shipment (HTTP %(code)s):\n%(body)s",
                code=resp.status_code, body=resp.text))
        return resp.json()

    def _dhlparcel_fetch_label(self, shipment_id, token):
        headers = {"Authorization": "Bearer " + token, "Accept": "application/pdf"}
        try:
            resp = requests.get(API_BASE + (LABEL_PATH % shipment_id),
                                headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise UserError(_("Could not fetch DHL label PDF: %s") % exc) from exc
        if resp.status_code != 200:
            raise UserError(_(
                "DHL Parcel label fetch failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        return resp.content

    # ------------------------------------------------------------------
    # payload builders
    # ------------------------------------------------------------------
    def _dhlparcel_build_receiver(self, partner):
        if not partner:
            raise UserError(_("The delivery has no customer address."))
        if not partner.country_id:
            raise UserError(_("Customer '%s' has no country set.") % partner.display_name)
        if not (partner.street and partner.zip and partner.city):
            raise UserError(_(
                "Customer '%s' address is incomplete (street / zip / city required)."
            ) % partner.display_name)
        street, number, addition = _extract_address(partner)
        first_name, last_name = _split_name(partner.name)
        return {
            "name": {
                "firstName": "" if partner.is_company else first_name,
                "lastName": "" if partner.is_company else (last_name or partner.name or ""),
                "companyName": partner.name if partner.is_company else "",
                "additionalName": "",
            },
            "address": {
                "countryCode": partner.country_id.code,
                "postalCode": partner.zip,
                "city": partner.city,
                "street": street,
                "number": number,
                "addition": addition,
                "isBusiness": partner.is_company,
            },
            "email": partner.email or "",
            "phoneNumber": partner.phone or partner.mobile or "",
        }

    def _dhlparcel_build_shipper(self, picking):
        # Native shipper: warehouse partner, falling back to company partner.
        partner = (picking.picking_type_id.warehouse_id.partner_id
                   or picking.company_id.partner_id)
        if not (partner and partner.street and partner.zip
                and partner.city and partner.country_id):
            raise UserError(_(
                "The warehouse / company address is incomplete; cannot build "
                "the DHL shipper address."))
        street, number, addition = _extract_address(partner)
        return {
            "name": {
                "firstName": "", "lastName": "",
                "companyName": partner.name or picking.company_id.name,
                "additionalName": "",
            },
            "address": {
                "countryCode": partner.country_id.code,
                "postalCode": partner.zip,
                "city": partner.city,
                "street": street,
                "number": number,
                "addition": addition,
                "isBusiness": True,
            },
            "email": partner.email or "",
            "phoneNumber": partner.phone or "",
        }

    def _dhlparcel_build_payload(self, picking, shipment_id, weights):
        """One shipment (multicollo): one piece per package in `weights`.
        DHL returns a trackerCode per piece and one multi-page label PDF."""
        ref = picking.origin or picking.name
        pieces = [{
            "parcelType": self.dhlparcel_default_parcel_type,
            "quantity": 1,
            "weight": w or 1.0,
        } for w in weights]
        return {
            "shipmentId": shipment_id,
            "orderReference": ref,
            "accountId": self.sudo().dhlparcel_account_id or "",
            "receiver": self._dhlparcel_build_receiver(picking.partner_id),
            "shipper": self._dhlparcel_build_shipper(picking),
            "options": [{"key": "REFERENCE", "input": ref}],
            # Leave product empty: DHL resolves it from the recipient/route.
            "product": "",
            "returnLabel": False,
            "pieces": pieces,
        }

    def _dhlparcel_extract_trackers(self, response):
        """All piece tracker codes from a (multicollo) shipment response."""
        trackers = [pc["trackerCode"] for pc in (response.get("pieces") or [])
                    if pc.get("trackerCode")]
        if not trackers and response.get("trackerCode"):
            trackers.append(response["trackerCode"])
        return trackers

    # ------------------------------------------------------------------
    # carrier API (called by Odoo's delivery framework)
    # ------------------------------------------------------------------
    def dhlparcel_rate_shipment(self, order):
        self.ensure_one()
        try:
            if self.dhlparcel_pricing_mode == "rule":
                price = self._get_price_available(order)
            else:
                price = self.dhlparcel_flat_price
        except UserError as exc:
            return {"success": False, "price": 0.0,
                    "error_message": str(exc), "warning_message": False}
        return {"success": True, "price": price,
                "error_message": False, "warning_message": False}

    def dhlparcel_send_shipping(self, pickings):
        res = []
        default_weight = self.dhlparcel_default_weight or 1.0
        for picking in pickings:
            token = self._dhlparcel_authenticate()
            # One Odoo delivery == one DHL shipment (multicollo): one piece per
            # package. Native packing decides the package count and weights;
            # fall back to a single default-weight piece when nothing is packed.
            try:
                packages = self._get_packages_from_picking(
                    picking, self.env["stock.package.type"])
                weights = [pkg.weight or default_weight for pkg in packages]
            except UserError:
                weights = [default_weight]

            shipment_id = str(uuid.uuid4())
            payload = self._dhlparcel_build_payload(picking, shipment_id, weights)
            response = self._dhlparcel_create_shipment(payload, token)
            trackers = self._dhlparcel_extract_trackers(response)

            # A single GET /labels/{shipmentId} returns all piece labels in one
            # multi-page PDF.
            try:
                pdf = self._dhlparcel_fetch_label(shipment_id, token)
                fname = "DHL-%s.pdf" % (trackers[0] if trackers else shipment_id[:8])
                picking.message_post(
                    body=_("DHL Parcel shipment created (%(n)s piece(s)). "
                           "Trackers: %(t)s")
                    % {"n": len(weights), "t": ", ".join(trackers) or "—"},
                    attachments=[(fname, pdf)])
            except UserError as exc:
                picking.message_post(body=_(
                    "DHL shipment created (trackers %(t)s) but the label PDF "
                    "could not be fetched: %(e)s")
                    % {"t": ", ".join(trackers) or "—", "e": exc})

            price = 0.0
            if picking.sale_id:
                rate = self.dhlparcel_rate_shipment(picking.sale_id)
                if rate.get("success"):
                    price = rate["price"]
            res.append({"exact_price": price,
                        "tracking_number": ", ".join(trackers)})
        return res

    def dhlparcel_get_tracking_link(self, picking):
        return TRACK_URL % (picking.carrier_tracking_ref or "")

    def dhlparcel_cancel_shipment(self, picking):
        # The Parcel API intervention/cancel flow is not wired in yet.
        picking.message_post(body=_(
            "DHL Parcel shipments must currently be cancelled in the DHL "
            "portal. The local tracking reference has been cleared."))
        picking.write({"carrier_tracking_ref": False})
