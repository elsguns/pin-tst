{
    'name': 'Running Scheduled Actions',
    'version': '17.0.1.0.0',
    'category': 'Technical',
    'summary': 'Adds a Running column to the scheduled actions tree view',
    'depends': ['base'],
    'data': ['views/ir_cron_views.xml'],
    'assets': {
        'web.assets_backend': [
            'running_scheduled_actions/static/src/js/cron_list_autorefresh.js',
            'running_scheduled_actions/static/src/css/cron.css',
        ],
    },
    'license': 'LGPL-3',
}
