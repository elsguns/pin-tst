import base64
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError


def _split_street(street):
    """Naive split of Odoo's combined street field into (street, number).
    Belgian convention: '<street> <number>[<letter>]'."""
    if not street:
        return "", ""
    match = re.search(r"^(.*?)\s+(\d+\w*)\s*$", street.strip())
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return street.strip(), ""


def _split_name(name):
    """Best-effort first/last name split."""
    parts = (name or "").strip().split(" ", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", name or ""


class DhlShipmentWizard(models.TransientModel):
    _name = "dhl.shipment.wizard"
    _description = "DHL Parcel shipment wizard"

    sale_order_id = fields.Many2one(
        "sale.order", required=True, readonly=True, ondelete="cascade",
    )
    partner_id = fields.Many2one(
        "res.partner", related="sale_order_id.partner_id", readonly=True,
    )
    partner_is_company = fields.Boolean(
        related="partner_id.is_company", readonly=True,
    )

    # Two selections, one shown depending on receiver type. Resolved into
    # `parcel_type` before sending to the API.
    parcel_type_consumer = fields.Selection(
        [
            ("XSMALL", "XSmall — mailbox parcel"),
            ("SMALL", "Small — regular parcel"),
            ("ENVELOPE", "Envelope"),
        ],
        string="Parcel type",
        default="SMALL",
    )
    parcel_type_business = fields.Selection(
        [
            ("XSMALL", "XSmall — mailbox parcel"),
            ("SMALL", "Small — regular parcel"),
            ("ENVELOPE", "Envelope"),
            ("PALLET", "Pallet"),
        ],
        string="Parcel type",
        default="SMALL",
    )
    parcel_type = fields.Char(
        compute="_compute_parcel_type",
        string="Resolved parcel type",
    )

    weight = fields.Float(
        string="Weight (kg)", default=1.0, required=True, digits=(8, 3),
    )
    quantity = fields.Integer(
        string="Pieces", default=1, required=True,
    )

    @api.depends("partner_is_company", "parcel_type_consumer", "parcel_type_business")
    def _compute_parcel_type(self):
        for wiz in self:
            wiz.parcel_type = (
                wiz.parcel_type_business if wiz.partner_is_company
                else wiz.parcel_type_consumer
            )

    def _build_receiver(self):
        p = self.partner_id
        if not p:
            raise UserError(_("Sale order has no customer."))
        if not p.country_id:
            raise UserError(_("Customer has no country set."))
        if not (p.street and p.zip and p.city):
            raise UserError(_(
                "Customer address is incomplete (street / zip / city required)."
            ))
        street, number = _split_street(p.street)
        first_name, last_name = _split_name(p.name)
        return {
            "name": {
                "firstName": "" if p.is_company else first_name,
                "lastName": "" if p.is_company else (last_name or p.name or ""),
                "companyName": p.name if p.is_company else "",
                "additionalName": "",
            },
            "address": {
                "countryCode": p.country_id.code,
                "postalCode": p.zip,
                "city": p.city,
                "street": street,
                "number": number,
                "addition": "",
                "isBusiness": p.is_company,
            },
            "email": p.email or "",
            "phoneNumber": p.phone or p.mobile or "",
        }

    def _build_shipper(self):
        get_param = self.env["ir.config_parameter"].sudo().get_param
        required = {
            "shipper_company": get_param("dhl_parcel_api.shipper_company"),
            "shipper_street": get_param("dhl_parcel_api.shipper_street"),
            "shipper_number": get_param("dhl_parcel_api.shipper_number"),
            "shipper_postal_code": get_param("dhl_parcel_api.shipper_postal_code"),
            "shipper_city": get_param("dhl_parcel_api.shipper_city"),
            "shipper_country_code": get_param("dhl_parcel_api.shipper_country_code"),
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise UserError(_(
                "Shipper address is incomplete in settings. Missing: %s"
            ) % ", ".join(missing))
        return {
            "name": {
                "firstName": "",
                "lastName": "",
                "companyName": required["shipper_company"],
                "additionalName": "",
            },
            "address": {
                "countryCode": required["shipper_country_code"],
                "postalCode": required["shipper_postal_code"],
                "city": required["shipper_city"],
                "street": required["shipper_street"],
                "number": required["shipper_number"],
                "addition": "",
                "isBusiness": True,
            },
            "email": get_param("dhl_parcel_api.shipper_email") or "",
            "phoneNumber": get_param("dhl_parcel_api.shipper_phone") or "",
        }

    def _build_payload(self, shipment_id, account_id):
        return {
            "shipmentId": shipment_id,
            "orderReference": self.sale_order_id.name,
            "accountId": account_id,
            "receiver": self._build_receiver(),
            "shipper": self._build_shipper(),
            "options": [
                {"key": "REFERENCE", "input": self.sale_order_id.name},
            ],
            "product": "",
            "returnLabel": False,
            "pieces": [
                {
                    "parcelType": self.parcel_type,
                    "quantity": self.quantity,
                    "weight": self.weight,
                },
            ],
        }

    def _extract_tracker_code(self, response):
        if response.get("trackerCode"):
            return response["trackerCode"]
        pieces = response.get("pieces") or []
        for piece in pieces:
            if piece.get("trackerCode"):
                return piece["trackerCode"]
        return ""

    def action_create_shipment(self):
        self.ensure_one()
        so = self.sale_order_id
        client = self.env["dhl.parcel.client"]
        _user_id, _key, account_id = client._get_credentials()

        # Re-use a previously stored shipment_id if the SO already had one
        # (idempotent retry); otherwise generate a fresh UUID.
        shipment_id = so.dhl_parcel_shipment_id or client.new_shipment_uuid()
        payload = self._build_payload(shipment_id, account_id)

        token, response = client.create_shipment(payload)
        tracker = self._extract_tracker_code(response)
        so.write({
            "dhl_parcel_shipment_id": shipment_id,
            "dhl_parcel_tracker_code": tracker,
        })

        try:
            pdf_bytes = client.fetch_label_pdf(shipment_id, token=token)
        except UserError as exc:
            so.message_post(body=_(
                "DHL shipment created (tracker: %(tracker)s), but the label PDF "
                "could not be fetched: %(error)s"
            ) % {"tracker": tracker or "—", "error": exc})
            return {"type": "ir.actions.act_window_close"}

        attachment = self.env["ir.attachment"].create({
            "name": "DHL-%s.pdf" % (tracker or shipment_id[:8]),
            "type": "binary",
            "datas": base64.b64encode(pdf_bytes),
            "res_model": "sale.order",
            "res_id": so.id,
            "mimetype": "application/pdf",
        })
        so.message_post(
            body=_("DHL shipment created. Tracker: %s") % (tracker or "—"),
            attachment_ids=[attachment.id],
        )
        return {"type": "ir.actions.act_window_close"}
