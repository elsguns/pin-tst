{
    'name': 'Vendor Stock Info (Oogachtend)',
    'version': '17.0.1.1.1',
    'category': 'Inventory/Purchase',
    'summary': 'Oogachtend (website 1) on-hand stock + lifecycle/availability block on the product page, shown only to administrators',
    'depends': ['product', 'website_sale'],
    'data': [
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'vendor_stock_info_oog/static/src/css/vendor_stock_info_oog.css',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
