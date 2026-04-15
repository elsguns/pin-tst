import logging
_logger = logging.getLogger(__name__)

from markupsafe import Markup
from odoo import models, fields, api

HBL_VISIBLE_AVAILABILITY = ['A']
HBL_WEBSITE_ID = 2
PINCEEL_VENDOR_ID = 4668


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    show_buy_button = fields.Boolean(compute='_compute_delivery_info')
    availability_msg = fields.Html(compute='_compute_delivery_info')
    availability_msg_class = fields.Char(compute='_compute_delivery_info')

    @api.depends_context('website_id')
    @api.depends('x_studio_lifecycle', 'qty_available', 'seller_ids')
    def _compute_delivery_info(self):
        website = self.env['website'].get_current_website()
        for p in self:
            if website.id != HBL_WEBSITE_ID:
                p.show_buy_button = True
                p.availability_msg = ''
                p.availability_msg_class = ''
                continue
            own_stock = p.sudo().qty_available
            vendor_infos = p.sudo().seller_ids.filtered(
                lambda s: s.company_id.id == 2
            ).sorted('sequence').read([
                'partner_id', 'vendor_stock', 'delay', 'x_studio_eta',
            ])
            vendor = self._pick_best_vendor(vendor_infos)
            show, msg, cls = self._buy_decision(
                own_stock, p.sudo().x_studio_lifecycle, vendor,
            )
            p.show_buy_button = show
            p.availability_msg = msg
            p.availability_msg_class = cls

    @api.model
    def _pick_best_vendor(self, vendor_infos):
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
        for vi in vendor_infos:
            if vi['partner_id'][0] == PINCEEL_VENDOR_ID:
                return vi
        return vendor_infos[0] if vendor_infos else None

    @api.model
    def _buy_decision(self, own_stock, lifecycle, vendor):
        """Returns (show_buy_button, message, css_class)."""
        if own_stock > 0:
            if lifecycle in ('4', '9'):
                return True, 'Laatste exemplaren!', 'vsi-last-copies'
            return (
                True,
                Markup('Vandaag besteld, overmorgen geleverd.'
                       '<br/>Meteen af te halen in de winkel.'),
                'vsi-in-stock',
            )

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
            return False, msg, 'vsi-announced'

        if lifecycle == '2':
            msg = 'Leverbaar binnen ' + delay_str
            if vendor and vendor.get('vendor_stock', 0) > 0:
                msg = Markup(msg + '.<br/>Afhaling binnen 1 dag.')
            return True, msg, 'vsi-available'

        if lifecycle == '3':
            msg = 'In herdruk'
            if eta_str:
                msg += '. Leverbaar vanaf ' + eta_str
            return False, msg, 'vsi-reprint'

        if lifecycle in ('4', '9'):
            return False, 'Uitverkocht', 'vsi-sold-out'

        if lifecycle == '5':
            return False, 'Uitgave geannuleerd', 'vsi-cancelled'

        return True, '', ''

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            domain.append(
                ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
            domain.append(
                ('x_studio_lifecycle', '!=', '0')
            )
        return domain