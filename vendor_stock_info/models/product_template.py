import logging
_logger = logging.getLogger(__name__)

from odoo import models, api

HBL_VISIBLE_AVAILABILITY = ['A', 'B', 'C', 'T', 'R']
HBL_WEBSITE_ID = 2


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            domain.append(
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
        return domain