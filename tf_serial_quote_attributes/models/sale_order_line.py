# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    tf_serial_plan_ids = fields.One2many(
        "tf.sale.serial.plan",
        "order_line_id",
        string="Serial Plan",
        readonly=True,
        copy=False,
    )

    tf_serial_plan_count = fields.Integer(
        compute="_compute_tf_serial_plan_count",
        string="Serials",
    )

    tf_is_serial_tracked = fields.Boolean(
        compute="_compute_tf_is_serial_tracked",
        string="Is Serial Tracked",
    )

    @api.depends("tf_serial_plan_ids")
    def _compute_tf_serial_plan_count(self):
        for line in self:
            line.tf_serial_plan_count = len(line.tf_serial_plan_ids)

    @api.depends("product_id.tracking")
    def _compute_tf_is_serial_tracked(self):
        for line in self:
            line.tf_is_serial_tracked = bool(line.product_id and line.product_id.tracking == "serial")

    def action_open_tf_serial_wizard(self):
        self.ensure_one()
        if not self._origin.id:
            raise UserError(_("Please save the quotation first, then open Serial Details."))
        if self.product_id.tracking != "serial":
            raise UserError(_("Serial Details is only available for products tracked by unique serial number."))
        if self.product_uom_qty <= 0:
            raise UserError(_("Quantity must be greater than 0 before opening Serial Details."))
        return {
            "type": "ir.actions.act_window",
            "name": "Serial Details",
            "res_model": "tf.sale.serial.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_line_id": self.id,
            },
        }
