# -*- coding: utf-8 -*-
from odoo import fields, models


class ProductLabelLayout(models.TransientModel):
    _inherit = 'product.label.layout'

    # New choice in the "Format" radio list of the Print Labels popup.
    # Key deliberately has no 'x' so the base _compute_dimensions() leaves
    # columns/rows at 1 (this label is one-per-page, not a sheet grid).
    print_format = fields.Selection(
        selection_add=[('l60_34', '60 x 34 mm')],
        ondelete={'l60_34': 'set default'},
    )

    def _prepare_report_data(self):
        xml_id, data = super()._prepare_report_data()
        if self.print_format == 'l60_34':
            xml_id = 'product_label_60x34.report_action_label_60x34'
        return xml_id, data
