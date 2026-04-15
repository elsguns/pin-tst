import logging
_logger = logging.getLogger(__name__)

from odoo import models, fields, api

HBL_VISIBLE_AVAILABILITY = ['A']
HBL_WEBSITE_ID = 2


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    delivery_message = fields.Char(compute='_compute_delivery_message')

    def _compute_delivery_message(self):
        for p in self:
            p.delivery_message = 'hello'

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            domain.append(
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
            domain.append(
                ('x_studio_lifecycle', '!=', '0')
            )
        return domain