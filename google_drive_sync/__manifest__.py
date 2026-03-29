{
    'name': 'Simple Google Drive',
    'version': '17.0.2.0.4',
    'category': 'Tools',
    'summary': 'Scan and selectively download Google Drive files',
    'description': """
        Browse and selectively download files from Google Drive folders.
        - Configure service account for authentication
        - Select specific folders to scan
        - Set time period for file detection
        - View list of available files
        - Download individual files on demand
        - Track download status
    """,
    'author': 'Your Name',
    'depends': ['base', 'base_setup'],
    'external_dependencies': {
        'python': ['google-auth', 'google-api-python-client'],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/gdrive_folder_views.xml',
        'views/gdrive_file_registry_views.xml',
        'views/actions.xml',
        'views/res_config_settings_views.xml',
        'views/gdrive_res_partner_views.xml',
        'views/isbn_lookup_wizard_views.xml',
        'views/menu.xml',
        'data/ir_cron.xml',
    ],
    'application': True,
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}