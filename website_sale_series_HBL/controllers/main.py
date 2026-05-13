import logging
import unicodedata

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

LETTERS = [chr(c) for c in range(ord('A'), ord('Z') + 1)]


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


class HBLSeriesController(http.Controller):

    @http.route(
        ['/shop/reeksen', '/shop/reeksen/<string:letter>'],
        type='http', auth='public', website=True, sitemap=False,
    )
    def series_index(self, letter=None, **kw):
        if letter is None:
            current = None
        else:
            up = letter.upper()
            current = up if up in LETTERS else None

        all_series = request.env['x_series'].sudo().search(
            [], order='x_name asc',
        )

        page_items = [s for s in all_series if _bucket_key(s.x_name) == current]

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
