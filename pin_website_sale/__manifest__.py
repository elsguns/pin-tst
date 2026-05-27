# -*- coding: utf-8 -*-
{
    'name': "pin_website_sale",

    'summary': "pin_website_sale",

    'description': """
Long description of module's purpose
    """,

    'author': "o.s.admin",
    'website': "https://www.osadmin.be",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/15.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Website',
    'version': '17.0.0.3',

    # any module necessary for this one to work correctly
    'depends': ['website_sale', 'vendor_stock_info'],

    # always loaded
    'data': [
        'views/templates.xml',
        'views/address_b2b_template.xml',
    ],
}

