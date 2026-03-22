from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleVendorStock(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        values = super()._prepare_product_values(product, category, search, **kwargs)
        vendor_infos = product.sudo().seller_ids.sorted('sequence').read([
            'partner_id', 'vendor_stock', 'delay',
        ])
        values['vendor_infos'] = vendor_infos
        return values
