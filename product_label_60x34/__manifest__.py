{
    'name': 'Product Label 60 x 34 mm',
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': 'Adds a 60 x 34 mm barcode label as a format option in the Print Labels popup',
    'description': """
Adds a "60 x 34 mm" choice to the Format radio list of the standard
Print Labels wizard (product.label.layout). Selecting it prints a
60x34mm barcode + product-name label, one label per page, honouring the
Quantity set in the popup. Reuses Odoo's native label data pipeline
(product.report.product_label_report._prepare_data).
""",
    'depends': ['stock'],
    'data': [
        'report/label_60x34_report.xml',
        'report/label_60x34_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
