# -*- coding: utf-8 -*-
from odoo import models
from odoo.addons.product.report.product_label_report import _prepare_data


class ReportProductLabel60x34(models.AbstractModel):
    _name = 'report.product_label_60x34.report_label_60x34'
    _description = 'Product Label Report 60 x 34 mm'

    def _get_report_values(self, docids, data):
        # Reuse Odoo's native label pipeline: turns the wizard's data dict
        # (quantity_by_product, layout_wizard, pricelist, ...) into the
        # {product: [(barcode, qty), ...]} structure the template renders.
        return _prepare_data(self.env, docids, data)
