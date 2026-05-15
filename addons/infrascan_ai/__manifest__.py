{
    'name': 'InfraScan AI Core',
    'summary': 'AI Integration for Thermal Analysis',
    'version': '1.2',
    'author': 'InfraScan',
    'depends': ['project', 'website'],
    'data': [
        'data/infrascan_config_data.xml',
        'views/project_task_views.xml',
        'views/res_partner_views.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'infrascan_ai/static/src/css/website_custom.css',
            'infrascan_ai/static/src/js/website_custom.js',
        ],
    },
    'installable': True,
    'license': 'LGPL-3',
}
