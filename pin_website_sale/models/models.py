from odoo import api, fields, models, _
from odoo.addons.vendor_stock_info.models.product_template import (
    HBL_VISIBLE_AVAILABILITY, HBL_WEBSITE_ID,
)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)
        search_fields = res['search_fields']
        search_fields.append('x_studio_publisher.x_name')
        search_fields.append('x_studio_author_ids.x_name')
        search_fields.append('x_studio_series_id.x_name')
        search_fields.append('product_variant_ids.barcode')
        search_fields.append('x_studio_title')
        if website.id == HBL_WEBSITE_ID:
            res['base_domain'].append([
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            ])
        return res


class Website(models.Model):
    _inherit = "website"

    @staticmethod
    def _get_product_sort_mapping():
        return [
            ('website_sequence asc', _('Featured')),
            ('x_studio_publish_week desc', _('Newest Arrivals')),
            ('name asc', _('Name (A-Z)')),
            # ('list_price asc', _('Price - Low to High')),
            # ('list_price desc', _('Price - High to Low')),
        ]

    shop_default_sort = fields.Selection(default='website_sequence asc')