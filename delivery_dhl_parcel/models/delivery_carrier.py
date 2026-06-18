import base64
import json
import logging
import re
import uuid
from datetime import datetime, timezone

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .dhl_parcel_line import BUSINESS_TYPES, CONSUMER_TYPES
from .dhl_parcel_tariff import ALL_PARCEL_TYPES

_logger = logging.getLogger(__name__)

API_BASE = "https://api-gw.dhlparcel.nl"
AUTH_PATH = "/authenticate/api-key"
SHIPMENTS_PATH = "/shipments"
LABEL_PATH = "/labels/%s"
TIMEOUT = 30
# Public consumer track & trace page. Requires both tracker code and
# receiver postcode; the older /traceer-uw-zending?tt= URL no longer
# resolves a real shipment view.
TRACK_URL = "https://my.dhlecommerce.nl/home/tracktrace/%(tracker)s/%(zip)s?lang=nl_NL"

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
# Per parcel-type recipient restriction; absent key = both consumer and business.
DHL_PARCEL_TYPE_RECIPIENT = {
    "ENVELOPE": "consumer",
    "XSMALL": "consumer",
    "PALLET": "business",
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
            ("ENVELOPE", "Envelope 50 to 500 g"),
            ("XSMALL", "Mailbox parcel"),
            ("SMALL", "Parcel up to 10 kg"),
            ("SMALL_MEDIUM", "Parcel up to 20 kg"),
            ("MEDIUM", "Parcel up to 31 kg"),
            ("PALLET", "Pallet up to 1000 kg"),
            ("MIX", "Mixed (pick parcels per shipment)"),
        ],
        string="Parcel type",
        help="The DHL parcel type for every shipment created through this "
             "shipping method. Create one shipping method per parcel type "
             "you offer. Pick 'Mixed' to combine several types in a single "
             "shipment — the delivery then exposes a DHL Parcels tab where "
             "you pick a type per parcel (just like the My DHL Parcel "
             "portal).")
    dhlparcel_last_error = fields.Text(
        "Last DHL API error", readonly=True, copy=False,
        help="The most recent DHL API error message for this carrier. "
             "Reset by clicking 'Clear last error'. Errors are always "
             "captured here regardless of the verbose-logging toggle.")
    dhlparcel_last_error_date = fields.Datetime(
        "Last error at", readonly=True, copy=False)
    dhlparcel_verbose_logging = fields.Boolean(
        "Verbose API logging", default=False,
        help="When enabled, every DHL Parcel API call (request URL, "
             "request body, response status and response body) is logged "
             "at INFO level. Credentials (User ID, API Key, Account ID) "
             "are redacted before logging. Logs go to both the Odoo "
             "server log file AND to Settings -> Technical -> Logging "
             "(visible without server access). Leave off in normal "
             "operation; switch on temporarily when troubleshooting, "
             "then off again to keep logs clean. Errors from the API "
             "are always logged regardless of this setting.")
    dhlparcel_default_weight = fields.Float(
        "Default weight (kg)", default=1.0,
        help="Used when a parcel's weight is 0 (e.g. products without a weight "
             "set). DHL refuses a 0 kg shipment, so this value is sent instead.")

    # Computed allowlist driving the Countries dropdown filter.
    dhlparcel_allowed_country_ids = fields.Many2many(
        "res.country",
        compute="_compute_dhlparcel_allowed_country_ids",
    )

    # Stored recipient restriction for views to filter on (e.g. hiding
    # consumer-only carriers when picking a method for a business partner).
    dhlparcel_recipient_restriction = fields.Selection(
        [("consumer", "Consumer only"), ("business", "Business only")],
        compute="_compute_dhlparcel_recipient_restriction",
        store=True,
    )

    @api.depends("delivery_type", "dhlparcel_parcel_type")
    def _compute_dhlparcel_recipient_restriction(self):
        for rec in self:
            if rec.delivery_type != "dhlparcel":
                rec.dhlparcel_recipient_restriction = False
                continue
            rec.dhlparcel_recipient_restriction = (
                DHL_PARCEL_TYPE_RECIPIENT.get(rec.dhlparcel_parcel_type) or False)

    # Per-type tariff for the MIX carrier. The cost of a mixed shipment is
    # sum(qty * tariff_for_type) over the DHL parcel lines on the picking.
    dhlparcel_tariff_ids = fields.One2many(
        "dhl.parcel.tariff", "carrier_id", string="Tarieven per type")

    @api.onchange("dhlparcel_parcel_type")
    def _onchange_dhlparcel_parcel_type_seed_tariffs(self):
        if (self.dhlparcel_parcel_type == "MIX"
                and not self.dhlparcel_tariff_ids):
            self.dhlparcel_tariff_ids = [
                (0, 0, {"parcel_type": code, "price": 0.0})
                for code, _label in ALL_PARCEL_TYPES
            ]

    @api.depends("delivery_type", "dhlparcel_parcel_type")
    def _compute_dhlparcel_allowed_country_ids(self):
        Country = self.env["res.country"]
        all_countries = Country.search([])
        dhl_countries = Country.search([("code", "in", DHL_COUNTRY_CODES)])
        for rec in self:
            if rec.delivery_type != "dhlparcel":
                rec.dhlparcel_allowed_country_ids = all_countries
                continue
            # MIX has no carrier-level country restriction; the per-line
            # ENVELOPE-vs-NL constraint covers that case.
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
                    "Pick a Parcel type on the DHL shipping method '%s'."
                ) % rec.name)
            unsupported = rec.country_ids.filtered(
                lambda c: c.code not in dhl_codes)
            if unsupported:
                raise ValidationError(_(
                    "DHL Parcel does not deliver to the following "
                    "countries: %s.\nRemove them from the Countries field."
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
                    "The parcel type '%(ptype)s' is only available for "
                    "shipments to %(allowed)s.\n"
                    "Remove these countries from the Countries field, or "
                    "pick a different parcel type: %(wrong)s"
                ) % {
                    "ptype": ptype_label,
                    "allowed": ", ".join(allowed_names),
                    "wrong": ", ".join(wrong.mapped("name")),
                })

    # ------------------------------------------------------------------
    # API plumbing
    # ------------------------------------------------------------------
    def _dhlparcel_redact(self, text):
        """Replace this carrier's credentials by ***REDACTED*** so we can
        safely write request/response bodies to the logs without leaking
        the User ID, API Key or Account ID."""
        if not text:
            return text
        out = str(text)
        carrier = self.sudo()
        for secret in (carrier.dhlparcel_api_key,
                       carrier.dhlparcel_user_id,
                       carrier.dhlparcel_account_id):
            if secret:
                out = out.replace(secret, "***REDACTED***")
        return out

    def _dhlparcel_log_api(self, method, url, status, response_text,
                           request_body=None, exception=None):
        """Log one DHL API exchange. Errors are always logged at WARNING
        (regardless of the verbose toggle). On success, log at INFO only
        when verbose mode is on. The same line is written to both the
        Python logger (server log file) and ir.logging (visible in
        Settings -> Technical -> Logging, so a customer can capture
        logs without server access)."""
        is_error = bool(exception) or (status and status >= 400)
        if not is_error and not self.dhlparcel_verbose_logging:
            return
        msg_parts = [f"[{self.name}] {method} {url}"]
        if status is not None:
            msg_parts.append(f"-> HTTP {status}")
        if exception:
            msg_parts.append(f"EXCEPTION: {exception}")
        if request_body is not None:
            body_str = json.dumps(request_body) if isinstance(
                request_body, dict) else str(request_body)
            redacted = self._dhlparcel_redact(body_str)[:2000]
            msg_parts.append("request: " + (redacted or "(empty)"))
        if response_text is not None:
            redacted = self._dhlparcel_redact(response_text)[:2000]
            msg_parts.append("response: " + (redacted or "(empty)"))
        msg = " | ".join(msg_parts)
        if is_error:
            _logger.warning(msg)
        else:
            _logger.info(msg)
        # Mirror to ir.logging + (on error) update the carrier's
        # last-error fields. Both writes go via a separate cursor so they
        # survive a rollback of the outer validate transaction — that
        # rollback is exactly when we most want the trail to persist.
        try:
            with self.env.registry.cursor() as new_cr:
                new_env = api.Environment(
                    new_cr, self.env.uid, self.env.context)
                new_env["ir.logging"].sudo().create({
                    "name": "delivery_dhl_parcel",
                    "type": "server",
                    "level": "WARNING" if is_error else "INFO",
                    "message": msg,
                    "path": "delivery_dhl_parcel",
                    "func": "dhlparcel_log_api",
                    "line": "0",
                    "dbname": new_cr.dbname,
                })
                if is_error:
                    new_env["delivery.carrier"].sudo().browse(self.id).write({
                        "dhlparcel_last_error": msg,
                        "dhlparcel_last_error_date": fields.Datetime.now(),
                    })
        except Exception:
            _logger.exception("Could not persist DHL API log to ir.logging")

    def _dhlparcel_authenticate(self):
        self.ensure_one()
        carrier = self.sudo()
        if not (carrier.dhlparcel_user_id and carrier.dhlparcel_api_key):
            raise UserError(_(
                "DHL Parcel credentials are not set on shipping method '%s'."
            ) % self.name)
        url = API_BASE + AUTH_PATH
        # Do not log the raw auth body even when verbose; it contains the
        # API key. Log only that an auth call was made.
        try:
            resp = requests.post(
                url,
                json={"userId": carrier.dhlparcel_user_id,
                      "key": carrier.dhlparcel_api_key},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            self._dhlparcel_log_api("POST", url, None, None,
                                    request_body="(credentials)",
                                    exception=exc)
            raise UserError(_("Could not reach DHL Parcel API: %s") % exc) from exc
        if resp.status_code != 200:
            self._dhlparcel_log_api("POST", url, resp.status_code, resp.text,
                                    request_body="(credentials)")
            raise UserError(_(
                "DHL Parcel authentication failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text))
        self._dhlparcel_log_api("POST", url, resp.status_code,
                                "(JWT token, redacted)",
                                request_body="(credentials)")
        token = resp.json().get("accessToken")
        if not token:
            raise UserError(_("DHL Parcel authentication returned no accessToken."))
        return token

    def _dhlparcel_create_shipment(self, payload, token):
        url = API_BASE + SHIPMENTS_PATH
        headers = {
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            resp = requests.post(url, json=payload,
                                 headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            self._dhlparcel_log_api("POST", url, None, None,
                                    request_body=payload, exception=exc)
            raise UserError(_("DHL Parcel API call failed: %s") % exc) from exc
        if resp.status_code not in (200, 201):
            self._dhlparcel_log_api("POST", url, resp.status_code, resp.text,
                                    request_body=payload)
            raise UserError(_(
                "DHL Parcel rejected the shipment (HTTP %(code)s):\n%(body)s",
                code=resp.status_code, body=resp.text))
        self._dhlparcel_log_api("POST", url, resp.status_code, resp.text,
                                request_body=payload)
        return resp.json()

    def _dhlparcel_fetch_label(self, label_id, token):
        url = API_BASE + (LABEL_PATH % label_id)
        headers = {"Authorization": "Bearer " + token, "Accept": "application/pdf"}
        try:
            resp = requests.get(url, headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            self._dhlparcel_log_api("GET", url, None, None, exception=exc)
            raise UserError(_("Could not fetch DHL label PDF: %s") % exc) from exc
        if resp.status_code != 200:
            self._dhlparcel_log_api("GET", url, resp.status_code,
                                    resp.text[:500])
            raise UserError(_(
                "DHL Parcel label fetch failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        self._dhlparcel_log_api(
            "GET", url, resp.status_code,
            f"(PDF, {len(resp.content)} bytes)")
        return resp.content

    def _dhlparcel_fetch_labels_multi(self, label_ids, token):
        """For shipments with multiple distinct pieces, GET /labels/{shipmentId}
        only returns the first piece's label. POST /labels/multi with all
        labelIds returns one combined PDF covering every piece."""
        url = API_BASE + "/labels/multi"
        headers = {"Authorization": "Bearer " + token,
                   "Content-Type": "application/json",
                   "Accept": "application/pdf"}
        body = {"labelIds": list(label_ids)}
        try:
            resp = requests.post(url, json=body,
                                 headers=headers, timeout=TIMEOUT)
        except requests.RequestException as exc:
            self._dhlparcel_log_api("POST", url, None, None,
                                    request_body=body, exception=exc)
            raise UserError(_("Could not fetch DHL combined label PDF: %s")
                            % exc) from exc
        if resp.status_code != 200:
            self._dhlparcel_log_api("POST", url, resp.status_code,
                                    resp.text[:500], request_body=body)
            raise UserError(_(
                "DHL Parcel multi-label fetch failed (HTTP %(code)s): %(body)s",
                code=resp.status_code, body=resp.text[:500]))
        self._dhlparcel_log_api(
            "POST", url, resp.status_code,
            f"(combined PDF, {len(resp.content)} bytes)",
            request_body=body)
        return resp.content

    # ------------------------------------------------------------------
    # payload builders
    # ------------------------------------------------------------------
    @staticmethod
    def _first(*values):
        """Return the first truthy value, or ''. Handy for email/phone
        fallback chains where the literal field may sit on the parent
        commercial partner rather than the delivery-address contact."""
        for v in values:
            if v:
                return v
        return ""

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
        # Delivery contacts are often children of a commercial partner and
        # carry no email/phone of their own; fall back to the commercial
        # partner so DHL gets a contact way to reach the recipient.
        commercial = partner.commercial_partner_id or partner
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
            "email": self._first(partner.email, commercial.email),
            "phoneNumber": self._first(
                partner.phone, partner.mobile,
                commercial.phone, commercial.mobile),
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
        # Warehouse partners are typically skeleton address records without
        # email/phone; fall back to the company partner (and the company
        # itself for email, which is a related field in core Odoo).
        company_partner = picking.company_id.partner_id
        company = picking.company_id
        return {
            "name": {
                "firstName": "", "lastName": "",
                "companyName": partner.name or company.name,
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
            "email": self._first(
                partner.email, company_partner.email, company.email),
            "phoneNumber": self._first(
                partner.phone, company_partner.phone, company.phone),
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

        - MIX carrier: one piece per dhl.parcel.line on the delivery
          (type/qty/weight from the line).
        - Otherwise: type is fixed by the carrier; one piece per package
          (Put-in-Pack), or a single piece with quantity=dhl_parcel_count.
        """
        ptype = self.dhlparcel_parcel_type
        if ptype == "MIX":
            return self._dhlparcel_pieces_from_lines(picking)
        self._dhlparcel_check_recipient_compat(ptype, picking.partner_id)
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

    def _dhlparcel_pieces_from_lines(self, picking):
        if not picking.dhl_parcel_line_ids:
            raise UserError(_(
                "Add at least one parcel in the DHL Parcels tab on this "
                "delivery, or pick a DHL shipping method with a fixed "
                "parcel type."))
        fallback_weight = self.dhlparcel_default_weight or 1.0
        pieces = []
        for line in picking.dhl_parcel_line_ids:
            ptype = line.parcel_type
            if not ptype:
                raise UserError(_(
                    "One of the parcels in the DHL Parcels tab has no "
                    "type. Set the type before validating."))
            self._dhlparcel_check_recipient_compat(ptype, picking.partner_id)
            weight = (line.weight
                      or self._dhlparcel_default_weight_for_type(ptype)
                      or fallback_weight)
            pieces.append({
                "parcelType": ptype,
                "quantity": line.quantity or 1,
                "weight": weight,
            })
        return pieces

    @staticmethod
    def _dhlparcel_check_recipient_compat(parcel_type, partner):
        """Raise UserError if the parcel type isn't sellable to this recipient
        kind (consumer-only types on a company, business-only on an individual).
        """
        restriction = DHL_PARCEL_TYPE_RECIPIENT.get(parcel_type)
        if not restriction:
            return
        type_label = dict(CONSUMER_TYPES + BUSINESS_TYPES).get(
            parcel_type, parcel_type)
        is_company = partner.is_company
        if restriction == "consumer" and is_company:
            raise UserError(_(
                "The parcel type '%(ptype)s' is only available for "
                "private recipients. '%(partner)s' is a company."
            ) % {"ptype": type_label, "partner": partner.display_name})
        if restriction == "business" and not is_company:
            raise UserError(_(
                "The parcel type '%(ptype)s' is only available for "
                "business recipients. '%(partner)s' is a private individual."
            ) % {"ptype": type_label, "partner": partner.display_name})

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

    def _dhlparcel_extract_label_ids(self, response):
        """All piece labelIds from a shipment response. Used to fetch the
        per-piece labels (the shipmentId-based fetch only returns the first
        piece's label)."""
        return [pc["labelId"] for pc in (response.get("pieces") or [])
                if pc.get("labelId")]

    # ------------------------------------------------------------------
    # carrier API (called by Odoo's delivery framework)
    # ------------------------------------------------------------------
    def dhlparcel_rate_shipment(self, order):
        self.ensure_one()
        warning = False
        try:
            if self.dhlparcel_parcel_type == "MIX":
                price, warning = self._dhlparcel_rate_mix(order)
            elif self.dhlparcel_pricing_mode == "rule":
                price = self._get_price_available(order)
            else:
                price = self.dhlparcel_flat_price
        except UserError as exc:
            return {"success": False, "price": 0.0,
                    "error_message": str(exc), "warning_message": False}
        return {"success": True, "price": price,
                "error_message": False, "warning_message": warning}

    def _dhlparcel_rate_mix(self, order):
        """Price for a MIX carrier = sum(qty * per-type tariff) over the
        parcel lines on this order's pickings. Returns (price, warning).
        When no parcel lines are defined yet (e.g. Add Shipping is run
        before the picking is filled in) the price is 0 and a warning is
        returned so the Add Shipping wizard surfaces it to the user."""
        tariff_by_type = {
            t.parcel_type: t.price for t in self.dhlparcel_tariff_ids}
        pickings = order.picking_ids.filtered(
            lambda p: p.dhl_parcel_line_ids)
        if not pickings:
            warning = _(
                "Er zijn nog geen parcels gedefinieerd in de DHL Parcels-"
                "tab van een delivery voor dit order — de verzendkost "
                "staat momenteel op 0,00.\n"
                "Doe Add Shipping opnieuw nadat het magazijn de DHL "
                "Parcels-tab heeft ingevuld om de juiste prijs te krijgen.")
            return 0.0, warning
        total = 0.0
        for picking in pickings:
            for line in picking.dhl_parcel_line_ids:
                rate = tariff_by_type.get(line.parcel_type, 0.0)
                total += (line.quantity or 1) * rate
        return total, False

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
            label_ids = self._dhlparcel_extract_label_ids(response)

            # GET /labels/{shipmentId} only returns the first piece's label
            # (DHL re-uses the shipmentId as the first labelId). For >1 piece
            # we POST /labels/multi with all labelIds to get a combined PDF.
            try:
                if len(label_ids) > 1:
                    pdf = self._dhlparcel_fetch_labels_multi(label_ids, token)
                else:
                    pdf = self._dhlparcel_fetch_label(
                        label_ids[0] if label_ids else shipment_id, token)
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
        # The MyDHL eCommerce track & trace page requires both the tracker
        # code and the receiver's postal code; without the postcode the
        # page returns a "no shipment found" error.
        tracker = (picking.carrier_tracking_ref or "").split(",")[0].strip()
        zip_code = (picking.partner_id.zip or "").replace(" ", "")
        if not tracker or not zip_code:
            return ""
        return TRACK_URL % {"tracker": tracker, "zip": zip_code}

    def dhlparcel_cancel_shipment(self, picking):
        # DHL's public API has no cancel endpoint (only a read-only
        # /intervention-options to ask whether a cancel would be allowed).
        # We keep carrier_tracking_ref intact so the operator can look the
        # shipment up in the portal, and post a chatter note explaining.
        picking.message_post(body=_(
            "Note: this does NOT cancel the shipment at DHL. DHL Parcel's "
            "public API does not expose a cancel endpoint, so the "
            "shipment(s) %s must be cancelled manually in the My DHL Parcel "
            "portal."
        ) % (picking.carrier_tracking_ref or "—"))

    # ------------------------------------------------------------------
    # Debug / diagnostics
    # ------------------------------------------------------------------
    _DHL_UUID_RE = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )

    def _dhlparcel_validate_credential_format(self):
        """Return a list of human-readable problems with the credential
        fields' format. DHL's auth endpoint cannot tell us which field is
        wrong (security), but we can at least catch typos and obviously
        invalid values before making an API call."""
        problems = []
        user_id = (self.dhlparcel_user_id or "").strip()
        api_key = (self.dhlparcel_api_key or "").strip()
        account_id = (self.sudo().dhlparcel_account_id or "").strip()

        if not user_id:
            problems.append(_("DHL User ID is empty."))
        elif not self._DHL_UUID_RE.match(user_id):
            problems.append(_(
                "DHL User ID does not look like a valid UUID "
                "(expected format: 12345678-1234-1234-1234-123456789012)."))

        if not api_key:
            problems.append(_("DHL API Key is empty."))
        elif not self._DHL_UUID_RE.match(api_key):
            problems.append(_(
                "DHL API Key does not look like a valid UUID "
                "(expected format: 12345678-1234-1234-1234-123456789012)."))

        if not account_id:
            problems.append(_("DHL Account ID is empty."))
        elif not account_id.isdigit():
            problems.append(_(
                "DHL Account ID should be a numeric customer number "
                "(e.g. 08500001), not %r.") % account_id)

        return problems

    def action_dhlparcel_test_connection(self):
        """Authenticate with the configured credentials and probe a
        read-only endpoint to confirm the token works end-to-end. Surfaces
        the JWT roles, account numbers and gateway response so the operator
        can self-diagnose credentials / permission issues before contacting
        support."""
        self.ensure_one()

        format_problems = self._dhlparcel_validate_credential_format()
        if format_problems:
            return self._dhlparcel_test_notification(
                title=_("DHL Parcel: credentials have format problems"),
                message=("\n".join("- " + p for p in format_problems) +
                         _("\n\nFix these in the Credentials section, then "
                           "click Test Connection again.")),
                kind="danger",
            )

        try:
            token = self._dhlparcel_authenticate()
        except UserError as exc:
            # All format checks passed but DHL still rejected the pair.
            # DHL's auth endpoint deliberately does not say which of User ID
            # / API Key is wrong (security: no enumeration).
            return self._dhlparcel_test_notification(
                title=_("DHL Parcel: authentication rejected"),
                message=_(
                    "User ID, API Key and Account ID are all in the right "
                    "format, but DHL did not accept the User ID + API Key "
                    "combination.\n\n"
                    "Likely cause: one of those two values does not match "
                    "what is currently active in My DHL Parcel -> Settings "
                    "-> API Keys. DHL's API on purpose does not tell us "
                    "which of the two is wrong.\n\n"
                    "DHL response: %s") % exc,
                kind="danger",
            )

        try:
            parts = token.split(".")
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except Exception as exc:
            claims = {}
            _logger.warning("Could not decode JWT: %s", exc)

        bu = claims.get("businessUnit", "?")
        roles = claims.get("roles") or []
        accounts = claims.get("accounts") or []
        exp_ts = claims.get("exp")
        exp_str = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            .strftime("%Y-%m-%d %H:%M UTC")
            if exp_ts else "?"
        )

        probe_url = (
            f"{API_BASE}/parcel-types/business/BE"
            f"?businessUnit={bu}&toCountry=BE"
            f"&carrier=DHL-PARCEL"
            f"&accountNumber={self.sudo().dhlparcel_account_id or ''}"
        )
        try:
            probe = requests.get(
                probe_url,
                headers={"Authorization": "Bearer " + token,
                         "Accept": "application/json"},
                timeout=TIMEOUT,
            )
            probe_line = (f"HTTP {probe.status_code} "
                          f"({len(probe.content)} bytes)")
            if probe.status_code != 200:
                probe_line += f" - body: {probe.text[:200]}"
        except requests.RequestException as exc:
            probe_line = f"call failed: {exc}"

        message = (
            f"Authentication OK.\n"
            f"Business unit: {bu}\n"
            f"Accounts on key: {', '.join(accounts) or '-'}\n"
            f"Configured Account ID: "
            f"{self.sudo().dhlparcel_account_id or '-'}\n"
            f"Roles: {', '.join(roles) or '-'}\n"
            f"Token expires: {exp_str}\n"
            f"Probe /parcel-types/business/BE: {probe_line}"
        )
        kind = ("success" if "label-service.B2X" in roles
                and "HTTP 200" in probe_line else "warning")
        return self._dhlparcel_test_notification(
            title=_("DHL Parcel: connection test"),
            message=message,
            kind=kind,
        )

    @staticmethod
    def _dhlparcel_test_notification(title, message, kind="success"):
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": title,
                "message": message,
                "type": kind,  # success | warning | danger | info
                "sticky": True,
            },
        }

    def action_dhlparcel_clear_last_error(self):
        """Reset the last-error fields on this carrier."""
        self.write({
            "dhlparcel_last_error": False,
            "dhlparcel_last_error_date": False,
        })
