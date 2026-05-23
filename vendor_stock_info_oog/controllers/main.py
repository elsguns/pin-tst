from odoo.http import request
from werkzeug.exceptions import NotFound
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.vendor_stock_info_oog.models.product_template import (
    OOG_VISIBLE_AVAILABILITY, OOG_WEBSITE_ID,
)


class WebsiteSaleVendorStockOog(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        if request.website.id != OOG_WEBSITE_ID:
            return super()._prepare_product_values(product, category, search, **kwargs)

        if (product.x_avail_oog not in OOG_VISIBLE_AVAILABILITY
                or product.x_studio_lifecycle == '0'):
            raise NotFound()

        values = super()._prepare_product_values(product, category, search, **kwargs)
        # Stock relies on on-hand quants only; no vendor stock is considered.
        values['own_stock'] = product.sudo().qty_available
        return values
