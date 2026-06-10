import logging
import re
import uuid

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

API_BASE = "https://api-gw.dhlparcel.nl"
AUTH_PATH = "/authenticate/api-key"
SHIPMENTS_PATH = "/shipments"
LABEL_PATH = "/labels/%s"
TIMEOUT = 30
# Public consumer track & trace page (tracker + postcode). Provisional URL.
TRACK_URL = "https://www.dhlparcel.nl/nl/consument/traceer-uw-zending?tt=%s"

# Countries DHL Parcel BE/NL/LU can deliver to (per the 2026-01-01 rate card).
DHL_COUNTRY_CODES = [
    "AT", "BE", "BG", "CH", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GB", "GR", "HR", "HU", "IE", "IT", "LI", "LT", "LU",
    "LV", "MC", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK", "SM",
]
# Per parcel-type country restrictions; absent key = all DHL_COUNTRY_CODES.
DHL_PARCEL_TYPE_COUNTRIES = {
    "ENVELOPE": ["NL"],
    "XSMALL": ["BE", "NL"],
}


def _split_number(token):
    """Split a house-number token into (number, addition).

    '88' -> ('88', ''); '88/3' -> ('88', '3'); '26B' -> ('26', 'B');
    '88 bus 3' -> ('88', 'bus 3'). Returns ('', token) if no leading digits.
    """
    m = re.match(r"^(\d+)\s*[/-]?\s*(.*)$", token.strip())
    if m:
        return m.group(1), m.group(2).strip()
    return "", token.strip()


def _extract_address(partner):
    """Best-effort (street, number, addition) from an Odoo partner.

    Handles: BE convention (number in street2), default Odoo (number in
    street, incl. '88/3' / '26B' forms), and mixed (number in street,
    addition in street2).
    """
    street = (partner.street or "").strip()
    street2 = (partner.street2 or "").strip()
    # Pattern A: street2 starts with the house number.
    if street2 and street2[:1].isdigit():
        number, addition = _split_number(street2)
        return street, number, addition
    # Pattern B: trailing house number embedded in street (\S* keeps '/3', 'B').
    m = re.search(r"^(.*?)\s+(\d+\S*)\s*$", street)
    if m:
        number, addition = _split_number(m.group(2))
        return m.group(1).strip(), number, (addition or street2)
    # Pattern C: nothing parseable.
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
    dhlparcel_parcel_type = fields.Selection(
        [
            ("ENVELOPE", "Envelop 50 tot 500 gram"),
            ("XSMALL", "Brievenbuspakket"),
            ("SMALL", "Pakket tot 10kg"),
            ("SMALL_MEDIUM", "Pakket tot 20kg"),
            ("MEDIUM", "Pakket tot 31kg"),
            ("PALLET", "Pallet tot 1000kg"),
        ],
        string="Parcel type",
        help="Het type van élk pakket dat met deze verzendmethode verzonden "
             "wordt. Maak één verzendmethode per parceltype dat je aanbiedt.")
    dhlparcel_default_weight = fields.Float(
        "Default weight (kg)", default=1.0,
        help="Used when a parcel's weight is 0 (e.g. products without a weight "
             "set). DHL refuses a 0 kg shipment, so this value is sent instead.")

    # Computed allowlist driving the Countries dropdown filter.
    dhlparcel_allowed_country_ids = fields.Many2many(
        "res.country",
        compute="_compute_dhlparcel_allowed_country_ids",
    )

    @api.depends("delivery_type", "dhlparcel_parcel_type")
    def _compute_dhlparcel_allowed_country_ids(self):
        Country = self.env["res.country"]
        all_countries = Country.search([])
        dhl_countries = Country.search([("code", "in", DHL_COUNTRY_CODES)])
        for rec in self:
            if rec.delivery_type != "dhlparcel":
                rec.dhlparcel_allowed_country_ids = all_countries
                continue
            restricted = DHL_PARCEL_TYPE_COUNTRIES.get(
                rec.dhlparcel_parcel_type)
            if restricted:
                rec.dhlparcel_allowed_country_ids = Country.search(
                    [("code", "in", restricted)])
            else:
                rec.dhlparcel_allowed_country_ids = dhl_countries

    @api.constrains(
        "delivery_type", "country_ids", "dhlparcel_parcel_type")
    def _check_dhlparcel_countries(self):
        Country = self.env["res.country"]
        dhl_codes = set(DHL_COUNTRY_CODES)
        for rec in self:
            if rec.delivery_type != "dhlparcel":
                continue
            if not rec.dhlparcel_parcel_type:
                raise ValidationError(_(
                    "Kies een Parcel type op de DHL-verzendmethode '%s'."
                ) % rec.name)
            unsupported = rec.country_ids.filtered(
                lambda c: c.code not in dhl_codes)
            if unsupported:
                raise ValidationError(_(
                    "DHL Parcel verzendt niet naar de volgende landen: %s.\n"
                    "Verwijder deze uit het Countries-veld."
                ) % ", ".join(unsupported.mapped("name")))
            restricted = DHL_PARCEL_TYPE_COUNTRIES.get(
                rec.dhlparcel_parcel_type)
            if not restricted:
                continue
            wrong = rec.country_ids.filtered(
                lambda c: c.code not in restricted)
            if wrong:
                ptype_label = dict(rec._fields[
                    "dhlparcel_parcel_type"].selection
                )[rec.dhlparcel_parcel_type]
                allowed_names = Country.search(
                    [("code", "in", restricted)]).mapped("name")
                raise ValidationError(_(
                    "Het parceltype '%(ptype)s' is enkel beschikbaar voor "
                    "zendingen naar %(allowed)s.\n"
                    "Verwijder deze landen uit het Countries-veld, of kies "
                    "een ander parceltype: %(wrong)s"
                ) % {
                    "ptype": ptype_label,
                    "allowed": ", ".join(allowed_names),
                    "wrong": ", ".join(wrong.mapped("name")),
                })

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

    @staticmethod
    def _dhlparcel_default_weight_for_type(parcel_type):
        """A representative in-tier weight per parcel type, used when the
        operator leaves both the picking weight and the carrier default at 0
        (so a Medium parcel is not declared as 0 kg)."""
        return {
            "ENVELOPE": 0.3,
            "XSMALL": 1.0,
            "SMALL": 5.0,
            "SMALL_MEDIUM": 15.0,
            "MEDIUM": 25.0,
            "PALLET": 200.0,
        }.get(parcel_type, 0.0)

    def _dhlparcel_pieces(self, picking):
        """Build the DHL `pieces` list for a picking.

        The carrier fixes the parcel type (one method per type). For the
        count: if Put-in-Pack created packages, one piece per package;
        otherwise we send a single piece with `quantity = dhl_parcel_count`
        (default 1).
        """
        ptype = self.dhlparcel_parcel_type
        type_default = self._dhlparcel_default_weight_for_type(ptype)
        fallback_weight = (
            self.dhlparcel_default_weight or type_default or 1.0)

        try:
            packages = self._get_packages_from_picking(
                picking, self.env["stock.package.type"])
        except UserError:
            packages = []
        if packages:
            return [
                {"parcelType": ptype, "quantity": 1,
                 "weight": pkg.weight or fallback_weight}
                for pkg in packages
            ]

        qty = max(int(picking.dhl_parcel_count or 1), 1)
        per_piece_weight = (
            (picking.weight / qty) if (picking.weight and qty) else 0
        ) or fallback_weight
        return [{"parcelType": ptype, "quantity": qty,
                 "weight": per_piece_weight}]

    def _dhlparcel_build_payload(self, picking, shipment_id, pieces):
        """One shipment (multicollo): `pieces` already built by
        _dhlparcel_pieces. DHL returns a trackerCode per piece and one
        multi-page label PDF."""
        ref = picking.origin or picking.name
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
        for picking in pickings:
            token = self._dhlparcel_authenticate()
            # One Odoo delivery == one DHL shipment (multicollo). The pieces
            # come from the DHL parcel lines, else native packages, else a
            # single auto piece.
            pieces = self._dhlparcel_pieces(picking)

            shipment_id = str(uuid.uuid4())
            payload = self._dhlparcel_build_payload(picking, shipment_id, pieces)
            response = self._dhlparcel_create_shipment(payload, token)
            trackers = self._dhlparcel_extract_trackers(response)

            # A single GET /labels/{shipmentId} returns all piece labels in one
            # multi-page PDF.
            try:
                pdf = self._dhlparcel_fetch_label(shipment_id, token)
                fname = "DHL-%s.pdf" % (trackers[0] if trackers else shipment_id[:8])
                piece_count = len(trackers) or sum(p["quantity"] for p in pieces)
                picking.message_post(
                    body=_("DHL Parcel shipment created (%(n)s piece(s)). "
                           "Trackers: %(t)s")
                    % {"n": piece_count, "t": ", ".join(trackers) or "—"},
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
        # The DHL intervention/cancel API is not wired in yet, so we cannot
        # cancel at DHL from here. Leave carrier_tracking_ref untouched (so the
        # standard cancel message still shows the tracker) and warn the user.
        picking.message_post(body=_(
            "Note: this does NOT cancel the shipment at DHL. The DHL "
            "cancellation API is not yet integrated, so the shipment(s) "
            "%s must be cancelled manually in the DHL portal."
        ) % (picking.carrier_tracking_ref or "—"))
