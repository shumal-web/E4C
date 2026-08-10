# -*- coding: utf-8 -*-
{
    "name": "TF Container Tracking Extends",
    "version": "19.0.1.1.0",
    "category": "Inventory/Sales",
    "summary": "Extends container tracking with relatable special instructions across Sale Order, Dispatch Tickets, Receiving, and Container Plans.",
    "author": "E4C",
    "license": "LGPL-3",
    "depends": ["tf_container_tracking"],
    "data": [
        "views/dispatch_views.xml",
        "views/stock_picking_views.xml",
        "views/container_dashboard_views.xml",
    ],
    "installable": True,
    "application": False,
}
