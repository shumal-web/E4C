# -*- coding: utf-8 -*-
from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    tf_flow_state = fields.Selection(
        copy=False,
        default="draft",
    )

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault("tf_flow_state", "draft")
        return super().copy(default=default)
