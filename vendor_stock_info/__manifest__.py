{
    'name': 'Vendor Stock Info',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Adds vendor stock field to supplierinfo and displays vendor details on product form',
    'depends': ['product', 'purchase'],
    'data': [
        'views/product_supplierinfo_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
