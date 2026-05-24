from odoo import api, fields, models

# Recipient-aware DHL parcel types (BE), mirroring the My DHL Parcel portal.
CONSUMER_TYPES = [
    ("ENVELOPE", "Envelope (50-500 g)"),
    ("XSMALL", "Mailbox parcel (max 2 kg)"),
    ("SMALL", "Parcel up to 10 kg"),
    ("SMALL_MEDIUM", "Parcel up to 20 kg"),
    ("MEDIUM", "Parcel up to 31 kg"),
]
BUSINESS_TYPES = [
    ("SMALL", "Parcel up to 10 kg"),
    ("SMALL_MEDIUM", "Parcel up to 20 kg"),
    ("MEDIUM", "Parcel up to 31 kg"),
    ("PALLET", "Pallet up to 1000 kg"),
]


class DhlParcelLine(models.Model):
    _name = "dhl.parcel.line"
    _description = "DHL Parcel (multicollo) line"

    picking_id = fields.Many2one(
        "stock.picking", required=True, ondelete="cascade", index=True)
    partner_is_company = fields.Boolean(
        related="picking_id.partner_id.is_company")

    # Two selections, one shown per recipient type; resolved into parcel_type.
    parcel_type_consumer = fields.Selection(
        CONSUMER_TYPES, string="Parcel type")
    parcel_type_business = fields.Selection(
        BUSINESS_TYPES, string="Parcel type")
    parcel_type = fields.Char(compute="_compute_parcel_type")

    quantity = fields.Integer(string="Qty", default=1, required=True)
    weight = fields.Float(
        string="Weight (kg)", digits=(8, 3),
        help="Optional. The carrier's default weight is used when blank.")

    @api.depends("partner_is_company", "parcel_type_consumer", "parcel_type_business")
    def _compute_parcel_type(self):
        for line in self:
            line.parcel_type = (
                line.parcel_type_business if line.partner_is_company
                else line.parcel_type_consumer)
