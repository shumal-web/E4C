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
    tf_address_note = fields.Text(
        string="Address",
        help="Default address copied to quotations created from this template.",
    )
    tf_shipper_note = fields.Text(
        string="Shipper",
        help="Default shipper details copied to quotations created from this template.",
    )
    tf_consignee_note = fields.Text(
        string="Consignee",
        help="Default consignee details copied to quotations created from this template.",
    )
    tf_special_instructions = fields.Text(
        string="Special Instructions",
        help="Default special request/instructions copied to quotations created from this template.",
    )
