# -*- coding: utf-8 -*-
{
    "name": "TF Container Tracking",
    "version": "19.0.2.7.0",
    "category": "Inventory/Sales",
    "summary": "Container serial planning, piece-to-container assignment, and tracking dashboard.",
    "author": "E4C",
    "license": "LGPL-3",
    "depends": ["tf_serial_quote_attributes", "sale_stock", "sale_management", "stock", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron.xml",
        "views/product_views.xml",
        "views/res_partner_views.xml",
        "views/sale_order_template_views.xml",
        "views/sale_order_views.xml",
        "views/sale_serial_wizard_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_move_line_views.xml",
        "views/stock_lot_views.xml",
        "views/container_dashboard_views.xml",
        "views/dispatch_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "tf_container_tracking/static/src/js/generate_serial_dialog_patch.js",
            "tf_container_tracking/static/src/js/tf_sale_serial_wizard_form.js",
            "tf_container_tracking/static/src/xml/generate_serial_dialog_patch.xml",
        ],
    },
    "installable": True,
    "application": False,
}
