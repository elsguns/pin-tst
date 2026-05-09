{
    'name': "dhl_ecommerce",

    'summary': """
    """,

    'description': """
        DHL eCommerce module for Odoo
    """,

    'author': "DHL eCommerce",
    'website': "https://www.dhlecommerce.nl",
    'license': 'LGPL-3',

    'category': 'DHL eCommerce',
    'version': '17.0.0.2.1',

    'depends': ['base', 'sale', 'sale_management', 'stock'],

    'data': [
        'views/res_config_settings_views.xml',
        'views/stock_pick_track_and_trace.xml',
        'views/sale_order_track_and_trace.xml',
    ],
}
