from odoo import fields, models


ALL_PARCEL_TYPES = [
    ("ENVELOPE", "Envelope 50 to 500 g"),
    ("XSMALL", "Mailbox parcel"),
    ("SMALL", "Parcel up to 10 kg"),
    ("SMALL_MEDIUM", "Parcel up to 20 kg"),
    ("MEDIUM", "Parcel up to 31 kg"),
    ("PALLET", "Pallet up to 1000 kg"),
]


class DhlParcelTariff(models.Model):
    _name = "dhl.parcel.tariff"
    _description = "DHL Parcel per-type tariff (for MIX carrier)"
    _order = "parcel_type"

    carrier_id = fields.Many2one(
        "delivery.carrier", required=True, ondelete="cascade", index=True)
    parcel_type = fields.Selection(
        ALL_PARCEL_TYPES, required=True, string="Parcel type")
    price = fields.Float(string="Price per parcel", default=0.0)

    _sql_constraints = [
        ("uniq_type_per_carrier",
         "unique(carrier_id, parcel_type)",
         "Each parcel type can only appear once per shipping method."),
    ]
