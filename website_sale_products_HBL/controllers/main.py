import logging

from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import WebsiteSale

_logger = logging.getLogger(__name__)


class WebsiteSaleProductsHBL(WebsiteSale):

    SECTIONS = [
        {
            'title': 'Nieuw',
            'attribute_value_ids': [8, 7],
            'attribs': ['4-8', '4-7'],
            'limit': 12,
        },
        {
            'title': 'Aangekondigd',
            'attribute_value_ids': [9],
            'attribs': ['4-9'],
            'limit': 12,
        },
    ]

    SECTION_TITLES = {
        frozenset([8, 7]): 'Nieuw',
        frozenset([9]): 'Aangekondigd',
    }

    def _is_shop_landing(self, category, search, **post):
        if category or search:
            return False
        if post.get('attrib'):
            return False
        return True

    @http.route()
    def shop(self, page=0, category=None, search='', min_price=0.0,
             max_price=0.0, ppg=False, **post):
        response = super().shop(
            page=page, category=category, search=search,
            min_price=min_price, max_price=max_price, ppg=ppg, **post,
        )

        if self._is_shop_landing(category, search, **post):
            website = request.website
            pricelist = response.qcontext.get('pricelist')
            fiscal_position = response.qcontext.get('fiscal_position')
            ProductTemplate = request.env['product.template']

            hbl_sections = []
            for sec in self.SECTIONS:
                ptav = request.env['product.template.attribute.value'].search([
                    ('product_attribute_value_id', 'in', sec['attribute_value_ids']),
                ])
                product_ids = ptav.mapped('product_tmpl_id').ids

                domain = [
                    ('id', 'in', product_ids),
                    ('sale_ok', '=', True),
                    ('website_published', '=', True),
                    ('website_id', 'in', (False, website.id)),
                ]
                products = ProductTemplate.search(
                    domain, limit=sec['limit'], order='create_date desc, name asc',
                )

                price_map = {}
                if products:
                    price_map = products._get_sales_prices(pricelist, fiscal_position)

                attrib_params = '&'.join(f'attrib={a}' for a in sec['attribs'])

                hbl_sections.append({
                    'title': sec['title'],
                    'product_list': products,
                    'price_map': price_map,
                    'view_all_url': f'/shop?{attrib_params}',
                })

            response.qcontext['hbl_sections'] = hbl_sections
            response.qcontext['hbl_is_landing'] = True
            response.qcontext['hbl_section_title'] = ''
        else:
            response.qcontext['hbl_sections'] = []
            response.qcontext['hbl_is_landing'] = False

            attrib_list = request.httprequest.args.getlist('attrib')
            active_value_ids = set()
            for a in attrib_list:
                try:
                    attr_id, val_id = a.split('-')
                    active_value_ids.add(int(val_id))
                except ValueError:
                    pass

            response.qcontext['hbl_section_title'] = self.SECTION_TITLES.get(
                frozenset(active_value_ids), ''
            )

        return response