from odoo.http import request
from werkzeug.exceptions import NotFound
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.vendor_stock_info.models.product_template import (
    HBL_VISIBLE_AVAILABILITY, HBL_WEBSITE_ID,
)

PINCEEL_VENDOR_ID = 4668


class WebsiteSaleVendorStock(WebsiteSale):

    def _prepare_product_values(self, product, category, search, **kwargs):
        if (request.website.id == HBL_WEBSITE_ID
                and product.x_studio_availability_hbl not in HBL_VISIBLE_AVAILABILITY):
            raise NotFound()

        values = super()._prepare_product_values(product, category, search, **kwargs)

        vendor_infos = product.sudo().seller_ids.filtered(
            lambda s: s.company_id.id == 2
        ).sorted('sequence').read([
            'partner_id', 'vendor_stock', 'delay', 'x_studio_eta',
        ])
        values['vendor_infos'] = vendor_infos
        values['own_stock'] = product.sudo().qty_available

        lifecycle = product.sudo().x_studio_lifecycle
        vendor = self._get_best_vendor(vendor_infos)
        show_buy, message, msg_color = self._compute_buy_decision(
            values['own_stock'], lifecycle, vendor,
        )
        values['show_buy_button'] = show_buy
        values['availability_msg'] = message
        values['availability_msg_color'] = msg_color
        return values

    def _get_best_vendor(self, vendor_infos):
        """Get Pinceel vendor if it has stock, otherwise best alternative."""
        for vi in vendor_infos:
            if vi['partner_id'][0] == PINCEEL_VENDOR_ID:
                if vi['vendor_stock'] > 0:
                    return vi
                break
        candidates = [
            vi for vi in vendor_infos
            if vi['partner_id'][0] != PINCEEL_VENDOR_ID and vi['vendor_stock'] > 0
        ]
        if candidates:
            return min(candidates, key=lambda v: v['delay'])
        # No vendor with stock — return Pinceel anyway for ETA
        for vi in vendor_infos:
            if vi['partner_id'][0] == PINCEEL_VENDOR_ID:
                return vi
        return vendor_infos[0] if vendor_infos else None

    def _compute_buy_decision(self, own_stock, lifecycle, vendor):
        """Returns (show_buy_button, message, color)."""
        if own_stock > 0:
            if lifecycle == '4':
                return True, 'Laatste exemplaren!', 'text-primary'
            return True, '', ''

        delay_str = ''
        eta_str = ''
        if vendor:
            delay = vendor.get('delay', 0)
            delay_str = '%s dag%s' % (delay, 'en' if delay != 1 else '')
            eta = vendor.get('x_studio_eta')
            if eta:
                eta_str = eta.strftime('%d/%m/%Y') if hasattr(eta, 'strftime') else str(eta)

        if lifecycle == '1':
            msg = 'Aangekondigd'
            if eta_str:
                msg += '. Leverbaar vanaf ' + eta_str
            return False, msg, 'text-success'

        if lifecycle == '2':
            msg = 'Leverbaar binnen ' + delay_str
            return True, msg, 'text-success'

        if lifecycle == '3':
            msg = 'In herdruk'
            if eta_str:
                msg += '. Leverbaar vanaf ' + eta_str
            return False, msg, 'text-success'

        if lifecycle == '4':
            return False, 'Uitverkocht', 'text-danger'

        if lifecycle == '5':
            return False, 'Uitgave geannuleerd', 'text-danger'

        return True, '', ''