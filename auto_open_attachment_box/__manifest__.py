{
    'name': 'Chatter Auto Open Attachments',
    'version': '19.0.1.0.0',
    'category': 'Discuss',
    'summary': 'Automatically open attachment box in chatter when attachments exist',
    'description': """
        Automatically open attachment box in Chatter by default when attachments exist on a record.
        Users do not need to click the paperclip icon to view attachments.
    """,
    'author': 'Antigravity',
    'depends': ['mail'],
    'assets': {
        'web.assets_backend': [
            'auto_open_attachment_box/static/src/chatter_patch.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
