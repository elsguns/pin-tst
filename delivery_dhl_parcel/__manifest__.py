{
    'name': "DHL Parcel Delivery Carrier",
    'summary': "DHL Parcel (Benelux) as an Odoo delivery method — labels created on delivery validation",
    'description': """
        Adds DHL Parcel (api-gw.dhlparcel.nl) as a delivery carrier
        (delivery_type = 'dhlparcel').

        - Credentials live on the shipping-method record (multi-account ready).
        - Shipping label is created when the delivery (stock.picking) is
          validated; the label PDF is attached to the picking and the tracker
          stored on the carrier_tracking_ref.
        - One shipment per package (native Odoo packages) for split deliveries.
        - Customer pricing is flat or weight-rule based (the DHL Parcel API
          does not expose live rates).

        Not affiliated with or endorsed by DHL.
    """,
    'author': "Bart Venken",
    'website': "https://bartvenken.be",
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'version': '17.0.0.1.0',
    'depends': ['stock_delivery'],
    'data': [
        'views/delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
}
