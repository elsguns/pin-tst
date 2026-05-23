import logging
_logger = logging.getLogger(__name__)

from odoo import models, fields, api

OOG_VISIBLE_AVAILABILITY = ['Y']
OOG_WEBSITE_ID = 1


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # _oog-suffixed so this module coexists with vendor_stock_info (HBL) in the
    # same database without their computed fields/methods colliding.
    show_buy_button_oog = fields.Boolean(compute='_compute_delivery_info_oog')
    avail_messages_oog = fields.Json(compute='_compute_delivery_info_oog')

    @api.depends_context('website_id')
    @api.depends('x_studio_lifecycle', 'qty_available')
    def _compute_delivery_info_oog(self):
        website = self.env['website'].get_current_website()
        for p in self:
            if website.id != OOG_WEBSITE_ID:
                p.show_buy_button_oog = True
                p.avail_messages_oog = []
                continue
            # Stock relies on on-hand quants only; no vendor stock is considered.
            own_stock = p.sudo().qty_available
            show, messages = self._buy_decision_oog(
                own_stock, own_stock, p.sudo().x_studio_lifecycle, None,
            )
            p.show_buy_button_oog = show
            p.avail_messages_oog = messages

    @api.model
    def _buy_decision_oog(self, total_stock, own_stock, lifecycle, vendor):
        """Returns (show_buy_button, [{'msg': ..., 'class': ...}, ...]).

        `vendor` is kept in the signature for message compatibility but is
        currently always None (this module does not use vendor lines), so
        delay/ETA text is simply omitted.
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
        eta_str = ''
        if vendor:
            delay = vendor.get('delay', 0)
            delay_str = '%d à %d dagen' % (delay + 1, delay + 2)
            eta = vendor.get('x_studio_eta')
            if eta:
                eta_str = eta.strftime('%d/%m/%Y') if hasattr(eta, 'strftime') else str(eta)

        if lifecycle == '1':
            msg = 'Aangekondigd'
            if eta_str:
                msg += '. Leverbaar vanaf ' + eta_str
            return False, [{'msg': msg, 'class': 'vsi-announced'}]

        if lifecycle == '2':
            messages = [{'msg': 'Geleverd binnen ' + delay_str, 'class': 'vsi-available'}]
            if vendor and vendor.get('vendor_stock', 0) > 0:
                messages.append({'msg': 'Morgen afhalen in de winkel', 'class': 'vsi-available'})
            return True, messages

        if lifecycle == '3':
            msg = 'In herdruk'
            if eta_str:
                msg += '. Leverbaar vanaf ' + eta_str
            return False, [{'msg': msg, 'class': 'vsi-reprint'}]

        if lifecycle in ('4', '9'):
            return False, [{'msg': 'Uitverkocht', 'class': 'vsi-sold-out'}]

        if lifecycle == '5':
            return False, [{'msg': 'Uitgave geannuleerd', 'class': 'vsi-cancelled'}]

        return True, []

    def _get_website_domain(self):
        domain = super()._get_website_domain()
        website = self.env['website'].get_current_website()
        if website.id == OOG_WEBSITE_ID:
            domain.append(
                ('x_avail_oog', 'in', OOG_VISIBLE_AVAILABILITY)
            )
            domain.append(
                ('x_studio_lifecycle', '!=', '0')
            )
        return domain
