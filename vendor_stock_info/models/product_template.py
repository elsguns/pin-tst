from odoo import models, api

# Values of x_studio_availability_hbl that should be visible on HBL website
# Adjust this list once the client decides
HBL_VISIBLE_AVAILABILITY = ['A', 'B', 'C', 'T', 'R']
HBL_WEBSITE_ID = 2


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            # Remove the is_published leaf from the domain
            # and replace with our custom field check
            domain = [
                leaf for leaf in domain
                if not (isinstance(leaf, (list, tuple)) and leaf[0] == 'is_published')
            ]
            domain.append(
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
        return domain