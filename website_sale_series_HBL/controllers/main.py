import logging
import re
import unicodedata

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.vendor_stock_info.models.product_template import (
    HBL_VISIBLE_AVAILABILITY, HBL_WEBSITE_ID,
)

_logger = logging.getLogger(__name__)

LETTERS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]
PPG = 20  # products per page on the series detail


def _bucket_key(name):
    """Return the alphabet bucket for a series name.

    Folds accented letters to their ASCII base (É → E, Ø → O, etc.).
    Anything that doesn't resolve to A–Z falls into the non-letter bucket,
    represented by None.
    """
    if not name:
        return None
    stripped = name.strip()
    if not stripped:
        return None
    first = stripped[0]
    for ch in unicodedata.normalize('NFD', first):
        upper = ch.upper()
        if 'A' <= upper <= 'Z':
            return upper
    return None


def _slugify(value):
    """URL-friendly slug from a series name.

    Lowercases, strips diacritics, replaces any run of non-alphanumeric chars
    with a single dash, trims leading/trailing dashes.
    """
    if not value:
        return ''
    decomposed = unicodedata.normalize('NFKD', value)
    ascii_only = ''.join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = ascii_only.encode('ascii', 'ignore').decode('ascii')
    s = re.sub(r'[^a-zA-Z0-9]+', '-', ascii_only).strip('-').lower()
    return s


class HBLSeriesController(http.Controller):

    @http.route(
        ['/shop/reeksen', '/shop/reeksen/<string:letter>'],
        type='http', auth='public', website=True, sitemap=False,
    )
    def series_index(self, letter=None, **kw):
        if request.website.id != HBL_WEBSITE_ID:
            raise NotFound()

        if letter is None:
            current = None
        else:
            up = letter.upper()
            current = up if up in LETTERS else None

        all_series = request.env['x_series'].sudo().search(
            [], order='x_name asc',
        )

        page_items = []
        for s in all_series:
            if _bucket_key(s.x_name) == current:
                page_items.append({
                    'name': s.x_name,
                    'url': '/shop/reeks/%s' % _slugify(s.x_name),
                })

        nav = [{
            'label': '#',
            'url': '/shop/reeksen',
            'active': current is None,
        }]
        for L in LETTERS:
            nav.append({
                'label': L,
                'url': '/shop/reeksen/%s' % L,
                'active': current == L,
            })

        return request.render('website_sale_series_HBL.series_index', {
            'nav': nav,
            'series_list': page_items,
            'current_label': '#' if current is None else current,
        })

    def _find_series_by_slug(self, series_slug):
        """Look up an x_series record whose slugified x_name matches.

        Brute-force scan; series count is in the hundreds–low thousands so this
        is fine. First match (lowest id) wins on collisions.
        """
        target = (series_slug or '').lower()
        all_series = request.env['x_series'].sudo().search([], order='id asc')
        for s in all_series:
            if _slugify(s.x_name) == target:
                return s
        return None

    @http.route(
        ['/shop/reeks/<string:series_slug>',
         '/shop/reeks/<string:series_slug>/page/<int:page>'],
        type='http', auth='public', website=True, sitemap=False,
    )
    def series_detail(self, series_slug, page=1, **kw):
        if request.website.id != HBL_WEBSITE_ID:
            raise NotFound()

        series = self._find_series_by_slug(series_slug)
        if not series:
            raise NotFound()

        website = request.website

        domain = [
            ('x_studio_series_id', '=', series.id),
            ('sale_ok', '=', True),
            ('website_published', '=', True),
            ('website_id', 'in', (False, website.id)),
            ('x_studio_availability_hbl', 'in', HBL_VISIBLE_AVAILABILITY),
        ]

        ProductTemplate = request.env['product.template']
        total = ProductTemplate.search_count(domain)

        pager = website.pager(
            url='/shop/reeks/%s' % series_slug,
            total=total,
            page=page,
            step=PPG,
        )

        products = ProductTemplate.search(
            domain,
            limit=PPG,
            offset=pager['offset'],
            order='x_studio_publish_week desc, name asc',
        )

        return request.render('website_sale_series_HBL.series_detail', {
            'series': series,
            'products': products,
            'pager': pager,
        })
