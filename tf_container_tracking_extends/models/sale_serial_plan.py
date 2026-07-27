# -*- coding: utf-8 -*-
from odoo import fields, models


class TfSaleSerialPlan(models.Model):
    _inherit = "tf.sale.serial.plan"

    tf_special_instructions = fields.Text(
        string="Special Instructions",
        related="order_id.tf_special_instructions",
        readonly=False,
        store=True,
    )
