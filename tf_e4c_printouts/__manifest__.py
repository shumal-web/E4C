# -*- coding: utf-8 -*-
{
    "name": "E4C Printouts",
    "version": "19.0.1.1.0",
    "category": "Inventory/Sales",
    "summary": "E4C BOL, truck sheets, export checklist, and receiving labels.",
    "author": "E4C",
    "license": "LGPL-3",
    "depends": ["tf_container_tracking_extends"],
    "data": [
        "report/e4c_printout_templates.xml",
        "report/e4c_printout_reports.xml",
        "views/stock_picking_views.xml",
        "views/dispatch_ticket_views.xml",
    ],
    "installable": True,
    "application": False,
}
