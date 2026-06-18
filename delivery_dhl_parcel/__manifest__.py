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
        - One shipping method per DHL parcel type (Mailbox parcel,
          Parcel up to 10 kg, ..., Pallet up to 1000 kg). The type is
          fixed by the method; create one method per type you offer.
        - Multicollo via either the "Number of parcels" field on the
          delivery (one piece type, count N) or native Put-in-Pack (one
          piece per package, all of the carrier's type).
        - Customer pricing is flat or weight-rule based (the DHL Parcel API
          does not expose live rates).

        Not affiliated with or endorsed by DHL.
    """,
    'author': "Bart Venken",
    'website': "https://bartvenken.be",
    'license': 'LGPL-3',
    'category': 'Inventory/Delivery',
    'version': '17.0.0.6.8',
    'depends': ['stock_delivery'],
    'data': [
        'security/ir.model.access.csv',
        'views/delivery_carrier_views.xml',
        'views/stock_picking_views.xml',
        'views/choose_delivery_carrier_views.xml',
    ],
    'installable': True,
    'application': False,
}
