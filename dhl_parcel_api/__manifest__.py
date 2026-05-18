{
    'name': "DHL Parcel API",
    'summary': "Create DHL Parcel shipments directly from a sale order via the DHL Parcel BE/NL/LU API",
    'description': """
        Adds a button on the sale order to create a shipment at DHL Parcel
        (api-gw.dhlparcel.nl). The tracker code is stored on the sale order
        and the label PDF is attached.

        This module talks to the DHL Parcel API directly (no external webhook
        middleware) and is intended as a replacement for the now-unmaintained
        dhl_ecommerce connector.
    """,
    'author': "Bart Venken",
    'website': "https://bartvenken.be",
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'version': '17.0.0.1.0',
    'depends': ['base', 'sale', 'sale_management', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'wizards/dhl_shipment_wizard_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
