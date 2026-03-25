from odoo.http import request
from werkzeug.exceptions import NotFound
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.vendor_stock_info.models.product_template import (
    HBL_VISIBLE_AVAILABILITY, HBL_WEBSITE_ID,
)

PINCEEL_VENDOR_ID = 4668


class WebsiteSaleVendorStock(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        # Block detail page for hidden products on HBL
        if (request.website.id == HBL_WEBSITE_ID
                and product.x_studio_availability_hbl not in HBL_VISIBLE_AVAILABILITY):
            raise NotFound()

        values = super()._prepare_product_values(product, category, search, **kwargs)

        vendor_infos = product.sudo().seller_ids.filtered(
            lambda s: s.company_id.id == 2
        ).sorted('sequence').read([
            'partner_id', 'vendor_stock', 'delay',
        ])
        values['vendor_infos'] = vendor_infos
        values['availability_msg'] = self._compute_availability_msg(vendor_infos)
        values['own_stock'] = product.sudo().qty_available
        return values

    def _compute_availability_msg(self, vendor_infos):
        # Check Pinceel first
        for vi in vendor_infos:
            if vi['partner_id'][0] == PINCEEL_VENDOR_ID:
                if vi['vendor_stock'] > 0:
                    return 'Leverbaar binnen %s dag%s' % (
                        vi['delay'], 'en' if vi['delay'] != 1 else ''
                    )
                break

        # Pinceel has no stock — find best alternative
        candidates = [
            vi for vi in vendor_infos
            if vi['partner_id'][0] != PINCEEL_VENDOR_ID and vi['vendor_stock'] > 0
        ]
        if candidates:
            best = min(candidates, key=lambda v: v['delay'])
            return 'Leverbaar binnen %s dag%s' % (
                best['delay'], 'en' if best['delay'] != 1 else ''
            )

        return ''