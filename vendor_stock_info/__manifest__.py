{
    'name': 'Vendor Stock Info',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Purchase',
    'summary': 'Adds vendor stock field to supplierinfo and displays vendor details on product form and webshop',
    'depends': ['product', 'purchase', 'website_sale'],
    'data': [
        'views/product_supplierinfo_views.xml',
        'views/templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
