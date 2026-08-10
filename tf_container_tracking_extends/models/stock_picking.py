# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tf_special_instructions = fields.Text(
        string="Special Instructions",
        related="tf_sale_order_id.tf_special_instructions",
        readonly=False,
        store=True,
    )
    tf_sale_tag_ids = fields.Many2many(
        string="Tags",
        related="tf_sale_order_id.tag_ids",
        readonly=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("tf_sale_order_id"):
                if vals.get("sale_id"):
                    vals["tf_sale_order_id"] = vals["sale_id"]
                elif vals.get("tf_container_plan_id"):
                    plan = self.env["tf.sale.serial.plan"].browse(vals["tf_container_plan_id"])
                    if plan.exists() and plan.order_id:
                        vals["tf_sale_order_id"] = plan.order_id.id
        return super().create(vals_list)

    def write(self, vals):
        res = super().write(vals)
        for picking in self:
            if not picking.tf_sale_order_id:
                target_so = picking.sale_id or (picking.tf_container_plan_id.order_id if picking.tf_container_plan_id else False)
                if target_so:
                    picking.tf_sale_order_id = target_so.id
        return res
