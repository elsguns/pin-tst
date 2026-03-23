from odoo import models, api

HBL_VISIBLE_AVAILABILITY = ['A', 'B', 'C', 'T', 'R']
HBL_WEBSITE_ID = 2


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            domain = [
                leaf for leaf in domain
                if not (isinstance(leaf, (list, tuple)) and leaf[0] == 'is_published')
            ]
            domain.append(
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
        return domain

    def _search_get_detail(self, website, order, options):
        result = super()._search_get_detail(website, order, options)
        if website.id == HBL_WEBSITE_ID:
            # Patch each domain in base_domain:
            # replace ('website_published', '=', True) with our availability filter
            new_domains = []
            for domain in result['base_domain']:
                patched = [
                    leaf for leaf in domain
                    if not (isinstance(leaf, (list, tuple))
                            and leaf[0] in ('website_published', 'is_published')
                            and leaf[2] == True)
                ]
                new_domains.append(patched)
            new_domains.append([
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            ])
            result['base_domain'] = new_domains
        return result