from odoo.addons.website_sale.controllers.main import WebsiteSale

PINCEEL_VENDOR_ID = 4668


class WebsiteSaleVendorStock(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        values = super()._prepare_product_values(product, category, search, **kwargs)
        vendor_infos = product.sudo().seller_ids.sorted('sequence').read([
            'partner_id', 'vendor_stock', 'delay',
        ])
        values['vendor_infos'] = vendor_infos
        values['availability_msg'] = self._compute_availability_msg(vendor_infos)
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