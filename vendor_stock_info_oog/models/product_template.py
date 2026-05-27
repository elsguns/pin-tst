import logging
_logger = logging.getLogger(__name__)

from odoo import models, fields, api

OOG_VISIBLE_AVAILABILITY = ['Y']
OOG_WEBSITE_ID = 1
# Lifecycle values that should appear at the end of the /shop listing
# (in herdruk / uitverkocht / uitgave geannuleerd / sold-out variant).
OOG_LIFECYCLE_END_GROUP = ('3', '4', '5', '9')


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # _oog-suffixed so this module coexists with vendor_stock_info (HBL) in the
    # same database without their computed fields/methods colliding.
    show_buy_button_oog = fields.Boolean(compute='_compute_delivery_info_oog')
    avail_messages_oog = fields.Json(compute='_compute_delivery_info_oog')

    # Stored bucket flag so the listing can ORDER BY it — Odoo's order parser
    # doesn't accept CASE WHEN, so we need a real column.
    x_lifecycle_end_oog = fields.Integer(
        compute='_compute_x_lifecycle_end_oog',
        store=True,
        index=True,
    )

    @api.depends('x_studio_lifecycle')
    def _compute_x_lifecycle_end_oog(self):
        for p in self:
            p.x_lifecycle_end_oog = 1 if p.x_studio_lifecycle in OOG_LIFECYCLE_END_GROUP else 0

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)
        if website.id == OOG_WEBSITE_ID:
            existing = res.get('order') or ''
            res['order'] = ('x_lifecycle_end_oog asc, ' + existing).rstrip(', ')
        return res

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
                own_stock, p.sudo().x_studio_lifecycle,
            )
            p.show_buy_button_oog = show
            p.avail_messages_oog = messages

    @api.model
    def _buy_decision_oog(self, stock, lifecycle):
        """Returns (show_buy_button, [{'msg': ..., 'class': ...}, ...]) for the
        Oogachtend website, based on on-hand stock + lifecycle only.
        """
        if stock > 0:
            if lifecycle in ('4', '9'):
                return True, [{'msg': 'Laatste exemplaren', 'class': 'vsi-last-copies'}]
            return True, []

        if lifecycle == '1':
            return False, [{'msg': 'Aangekondigd', 'class': 'vsi-announced'}]
        if lifecycle == '2':
            return True, []
        if lifecycle == '3':
            return False, [{'msg': 'In herdruk', 'class': 'vsi-reprint'}]
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
