from odoo import fields, models


ALL_PARCEL_TYPES = [
    ("ENVELOPE", "Envelop 50 tot 500 gram"),
    ("XSMALL", "Brievenbuspakket"),
    ("SMALL", "Pakket tot 10kg"),
    ("SMALL_MEDIUM", "Pakket tot 20kg"),
    ("MEDIUM", "Pakket tot 31kg"),
    ("PALLET", "Pallet tot 1000kg"),
]


class DhlParcelTariff(models.Model):
    _name = "dhl.parcel.tariff"
    _description = "DHL Parcel per-type tariff (for MIX carrier)"
    _order = "parcel_type"

    carrier_id = fields.Many2one(
        "delivery.carrier", required=True, ondelete="cascade", index=True)
    parcel_type = fields.Selection(
        ALL_PARCEL_TYPES, required=True, string="Parcel type")
    price = fields.Float(string="Prijs per pakket", default=0.0)

    _sql_constraints = [
        ("uniq_type_per_carrier",
         "unique(carrier_id, parcel_type)",
         "Each parcel type can only appear once per shipping method."),
    ]
