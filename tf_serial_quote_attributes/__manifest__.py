# -*- coding: utf-8 -*-
{
    "name": "TF Serial Planning on Quotation + Storage Attributes",
    "version": "19.0.2.0.0",
    "category": "Inventory/Sales",
    "summary": "Plan serials on quotation, edit on receipt, auto-fill delivery lots, day counter, POD, 1-page per serial print.",
    "author": "E4C",
    "license": "LGPL-3",
    "depends": ["sale_stock", "stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/sale_order_views.xml",
        "views/stock_views.xml",
        "views/stock_lot_views.xml",
        "wizard/sale_serial_wizard_views.xml",
        "report/serial_report.xml",
        "report/serial_report_template.xml",
        "report/receipt_serial_label_report.xml",
        "report/receipt_serial_label_template.xml",
    ],
    "installable": True,
    "application": False,
}
