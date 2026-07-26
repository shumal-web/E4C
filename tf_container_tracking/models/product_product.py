# -*- coding: utf-8 -*-
from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "type" in fields_list:
            res["type"] = "service"
        return res
