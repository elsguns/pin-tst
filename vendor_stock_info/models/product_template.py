import logging
_logger = logging.getLogger(__name__)

from odoo import models, fields, api

HBL_VISIBLE_AVAILABILITY = ['Y']
HBL_WEBSITE_ID = 2
PINCEEL_VENDOR_ID = 4668


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    show_buy_button = fields.Boolean(compute='_compute_delivery_info')
    avail_messages = fields.Json(compute='_compute_delivery_info')

    @api.depends_context('website_id')
    @api.depends('x_studio_lifecycle', 'qty_available', 'seller_ids',
                 'x_studio_publish_date', 'x_studio_reprint_date')
    def _compute_delivery_info(self):
        website = self.env['website'].get_current_website()
        for p in self:
            if website.id != HBL_WEBSITE_ID:
                p.show_buy_button = True
                p.avail_messages = []
                continue
            ps = p.sudo()
            own_stock = ps.qty_available
            vendor_infos = ps.seller_ids.filtered(
                lambda s: s.company_id.id == 2
            ).sorted('sequence').read([
                'partner_id', 'vendor_stock', 'delay', 'x_studio_eta',
            ])
            total_stock = own_stock + sum(vi['vendor_stock'] for vi in vendor_infos)
            vendor = self._pick_best_vendor(vendor_infos)
            show, messages = self._buy_decision(
                total_stock, own_stock, ps.x_studio_lifecycle, vendor,
                getattr(ps, 'x_studio_publish_date', False),
                getattr(ps, 'x_studio_reprint_date', False),
            )
            p.show_buy_button = show
            p.avail_messages = messages

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
    def _buy_decision(self, total_stock, own_stock, lifecycle, vendor,
                      publish_date, reprint_date):
        """Returns (show_buy_button, [{'msg': ..., 'class': ...}, ...]).

        publish_date / reprint_date come from product.template Studio fields
        (x_studio_publish_date / x_studio_reprint_date) and drive the
        "Leverbaar vanaf ..." suffix on Aangekondigd / In herdruk messages.
        Vendor is still used for lifecycle 2's delay text and the in-store
        pickup hint, but no longer for ETA dates.
        """
        if total_stock > 0:
            if lifecycle in ('4', '9'):
                return True, [{'msg': 'Laatste exemplaren!', 'class': 'vsi-last-copies'}]
            pickup_msg = (
                'Meteen af te halen in de winkel.' if own_stock > 0
                else 'Morgen afhalen in de winkel.'
            )
            return True, [
                {'msg': 'Vandaag besteld, overmorgen geleverd.', 'class': 'vsi-in-stock'},
                {'msg': pickup_msg, 'class': 'vsi-in-stock'},
            ]

        delay_str = ''
        if vendor:
            delay = vendor.get('delay', 0)
            delay_str = '%d à %d dagen' % (delay + 1, delay + 2)

        if lifecycle == '1':
            msg = 'Aangekondigd'
            if publish_date:
                msg += '. Leverbaar vanaf ' + publish_date.strftime('%d-%m-%Y')
            return False, [{'msg': msg, 'class': 'vsi-announced'}]

        if lifecycle == '2':
            messages = [{'msg': 'Geleverd binnen ' + delay_str, 'class': 'vsi-available'}]
            if vendor and vendor.get('vendor_stock', 0) > 0:
                messages.append({'msg': 'Morgen afhalen in de winkel', 'class': 'vsi-available'})
            return True, messages

        if lifecycle == '3':
            msg = 'In herdruk'
            if reprint_date:
                msg += '. Leverbaar vanaf ' + reprint_date.strftime('%d-%m-%Y')
            return False, [{'msg': msg, 'class': 'vsi-reprint'}]

        if lifecycle in ('4', '9'):
            return False, [{'msg': 'Uitverkocht', 'class': 'vsi-sold-out'}]

        if lifecycle == '5':
            return False, [{'msg': 'Uitgave geannuleerd', 'class': 'vsi-cancelled'}]

        return True, []

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == HBL_WEBSITE_ID:
            domain.append(
                ('x_avail_hbl', 'in', HBL_VISIBLE_AVAILABILITY)
            )
            domain.append(
                ('x_studio_lifecycle', '!=', '0')
            )
        return domain
