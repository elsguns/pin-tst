from odoo import fields, models


class ProductSupplierinfo(models.Model):
    _inherit = 'product.supplierinfo'

    vendor_stock = fields.Integer(
        string='Vendor Stock',
        default=0,
        help='Current stock level at the vendor',
    )
