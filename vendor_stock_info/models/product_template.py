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

    def _search_get_detail(self, website, order, options):
        result = super()._search_get_detail(website, order, options)
        if website.id == HBL_WEBSITE_ID:
            result['base_domain'].append([
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            ])
        return result