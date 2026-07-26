# -*- coding: utf-8 -*-
from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _tf_is_custom_logistics_line(self):
        self.ensure_one()
        product = self.product_id.product_tmpl_id
        return bool(product.tf_is_container or product.tf_requires_container)

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        custom_lines = self.filtered(lambda line: line._tf_is_custom_logistics_line())
        regular_lines = self - custom_lines
        if not regular_lines:
            return True
        return super(SaleOrderLine, regular_lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty
        )

    def action_open_tf_serial_wizard(self):
        action = super().action_open_tf_serial_wizard()
        self.ensure_one()
        if self.product_id.product_tmpl_id.tf_is_container:
            container_view = self.env.ref("tf_container_tracking.view_tf_sale_serial_wizard_form_container")
            action["view_id"] = container_view.id
            action["views"] = [(container_view.id, "form")]
        else:
            base_view = self.env.ref("tf_serial_quote_attributes.view_tf_sale_serial_wizard_form")
            action["view_id"] = base_view.id
            action["views"] = [(base_view.id, "form")]
        return action
