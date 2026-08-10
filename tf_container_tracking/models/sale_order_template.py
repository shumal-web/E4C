# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    tf_shipment_type = fields.Selection(
        [
            ("import", "Import"),
            ("export", "Export"),
        ],
        string="Flow Type",
        default="import",
        required=True,
        help="Default import/export flow applied when this template is selected on a quotation.",
    )
