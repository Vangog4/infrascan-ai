{
    'name': 'InfraScan AI Core',
    'summary': 'AI Thermal Diagnostics — auto-notifications, cron digests, Gemini analysis',
    'version': '1.3',
    'author': 'InfraScan',
    'depends': ['project', 'website'],
    'data': [
        'data/infrascan_config_data.xml',
        'data/project_stage_data.xml',
        'data/ir_cron.xml',
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
