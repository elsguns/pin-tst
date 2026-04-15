from odoo.http import request
from werkzeug.exceptions import NotFound
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.vendor_stock_info.models.product_template import (
    HBL_VISIBLE_AVAILABILITY, HBL_WEBSITE_ID,
)


class WebsiteSaleVendorStock(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        if request.website.id != HBL_WEBSITE_ID:
            return super()._prepare_product_values(product, category, search, **kwargs)

        if (product.x_studio_availability_hbl not in HBL_VISIBLE_AVAILABILITY
                or product.x_studio_lifecycle == '0'):
            raise NotFound()

        values = super()._prepare_product_values(product, category, search, **kwargs)

        vendor_infos = product.sudo().seller_ids.filtered(
            lambda s: s.company_id.id == 2
        ).sorted('sequence').read([
            'partner_id', 'vendor_stock', 'delay', 'x_studio_eta',
        ])
        values['vendor_infos'] = vendor_infos
        values['own_stock'] = product.sudo().qty_available
        return values
