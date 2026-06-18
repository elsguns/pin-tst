import base64
import json
import logging

import odoo
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    dhl_is_dhlparcel = fields.Boolean(
        compute="_compute_dhl_is_dhlparcel")
    dhl_carrier_parcel_type = fields.Selection(
        related="carrier_id.dhlparcel_parcel_type")
    dhl_partner_is_company = fields.Boolean(
        related="partner_id.is_company",
        help="Drives the recipient-aware parcel-type columns on the "
             "DHL Parcels lines.")
    dhl_partner_country_id = fields.Many2one(
        "res.country", related="partner_id.country_id")
    dhl_parcel_count = fields.Integer(
        string="Aantal pakketten", default=1,
        help="Aantal identieke pakketten in deze zending (multicollo). "
             "Genegeerd zodra je Put in Pack gebruikt: dan bepalen de "
             "aangemaakte packages het aantal pieces.")
    dhl_parcel_line_ids = fields.One2many(
        "dhl.parcel.line", "picking_id", string="DHL Parcels",
        help="Used only for DHL methods with parcel type 'Gemengd' (MIX): "
             "one row per parcel, type + qty + optional weight.")

    @api.depends("carrier_id", "carrier_id.delivery_type")
    def _compute_dhl_is_dhlparcel(self):
        for picking in self:
            picking.dhl_is_dhlparcel = (
                picking.carrier_id.delivery_type == "dhlparcel")

    def action_dhlparcel_export_debug_bundle(self):
        """Produce a single JSON file with everything support needs to
        understand what went (or would go) wrong for this picking, with
        no DHL credentials inside. The file is created as an attachment
        on the picking and the action returns an URL to download it."""
        self.ensure_one()
        carrier = self.carrier_id
        if not carrier or carrier.delivery_type != "dhlparcel":
            raise UserError(_(
                "This picking does not use a DHL Parcel carrier; "
                "nothing to export."))

        partner = self.partner_id
        commercial = partner.commercial_partner_id if partner else partner

        bundle = {
            "exported_at": fields.Datetime.now().isoformat(),
            "odoo_version": odoo.release.version,
            "module_version": self.env["ir.module.module"].sudo().search(
                [("name", "=", "delivery_dhl_parcel")],
                limit=1).installed_version or "?",
            "picking": {
                "id": self.id,
                "name": self.name,
                "state": self.state,
                "company": self.company_id.name,
                "warehouse": (self.picking_type_id.warehouse_id.name
                              if self.picking_type_id else None),
                "scheduled_date": str(self.scheduled_date or ""),
                "carrier_tracking_ref": self.carrier_tracking_ref,
                "weight": self.weight,
            },
            "carrier": {
                "name": carrier.name,
                "parcel_type": carrier.dhlparcel_parcel_type,
                "default_weight": carrier.dhlparcel_default_weight,
                "pricing_mode": carrier.dhlparcel_pricing_mode,
                "flat_price": carrier.dhlparcel_flat_price,
                "verbose_logging": carrier.dhlparcel_verbose_logging,
                "countries": carrier.country_ids.mapped("code"),
                "credentials_set": bool(
                    carrier.sudo().dhlparcel_user_id
                    and carrier.sudo().dhlparcel_api_key),
                "credentials_format_problems":
                    carrier._dhlparcel_validate_credential_format(),
                "last_error_date": str(
                    carrier.dhlparcel_last_error_date or ""),
                "last_error": carrier.dhlparcel_last_error,
            },
            "recipient": {
                "name": partner.name if partner else None,
                "is_company": partner.is_company if partner else None,
                "country": (partner.country_id.code
                            if partner and partner.country_id else None),
                "zip": partner.zip if partner else None,
                "city": partner.city if partner else None,
                "street_set": bool(partner.street) if partner else None,
                "email_set": bool(partner.email) if partner else None,
                "phone_set": bool(partner.phone or partner.mobile)
                            if partner else None,
                "commercial_partner_email_set": (
                    bool(commercial.email) if commercial else None),
            },
            "multicollo": {
                "dhl_parcel_count": self.dhl_parcel_count,
                "dhl_parcel_lines": [
                    {"type_consumer": l.parcel_type_consumer,
                     "type_business": l.parcel_type_business,
                     "resolved_type": l.parcel_type,
                     "quantity": l.quantity,
                     "weight": l.weight}
                    for l in self.dhl_parcel_line_ids
                ],
                "native_packages": [
                    {"name": p.name, "weight": p.weight,
                     "package_type": p.package_type_id.name or None}
                    for p in self.move_line_ids.mapped("result_package_id")
                ],
            },
            "would_send": {},
            "attachments_on_picking": [
                {"name": a.name, "size": a.file_size,
                 "mimetype": a.mimetype, "create_date": str(a.create_date)}
                for a in self.env["ir.attachment"].sudo().search([
                    ("res_model", "=", "stock.picking"),
                    ("res_id", "=", self.id),
                ])
            ],
        }

        # What we would send to DHL right now, without actually calling it.
        try:
            bundle["would_send"]["pieces"] = carrier._dhlparcel_pieces(self)
        except Exception as exc:
            bundle["would_send"]["pieces_error"] = str(exc)
        try:
            bundle["would_send"]["receiver"] = carrier._dhlparcel_build_receiver(
                self.partner_id)
        except Exception as exc:
            bundle["would_send"]["receiver_error"] = str(exc)
        try:
            bundle["would_send"]["shipper"] = carrier._dhlparcel_build_shipper(
                self)
        except Exception as exc:
            bundle["would_send"]["shipper_error"] = str(exc)

        payload = json.dumps(bundle, indent=2, default=str)
        ts = fields.Datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = "dhl-debug-{name}-{ts}.json".format(
            name=(self.name or "picking").replace("/", "-"), ts=ts)
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(payload.encode("utf-8")),
            "res_model": "stock.picking",
            "res_id": self.id,
            "mimetype": "application/json",
        })
        self.message_post(
            body=_("DHL debug bundle exported: %s") % filename,
            attachment_ids=[attachment.id],
        )
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/{}?download=true".format(attachment.id),
            "target": "self",
        }


