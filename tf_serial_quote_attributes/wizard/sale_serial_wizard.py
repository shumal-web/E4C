# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TfSaleSerialWizard(models.TransientModel):
    _name = "tf.sale.serial.wizard"
    _description = "TF Sale Serial Wizard"

    order_line_id = fields.Many2one("sale.order.line", required=True)
    order_id = fields.Many2one(related="order_line_id.order_id", readonly=True)
    product_id = fields.Many2one(related="order_line_id.product_id", readonly=True)
    qty = fields.Float(related="order_line_id.product_uom_qty", readonly=True)

    line_ids = fields.One2many("tf.sale.serial.wizard.line", "wizard_id", string="Serials")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_line_id = self.env.context.get("default_order_line_id")
        if order_line_id:
            sol = self.env["sale.order.line"].browse(order_line_id)
            res["order_line_id"] = sol.id

            # Load existing planned serials
            lines = []
            for pl in sol.tf_serial_plan_ids:
                lines.append((0, 0, {
                    "sequence": pl.sequence,
                    "serial_name": pl.serial_name,
                    "tf_description": pl.tf_description,
                    "tf_length": pl.tf_length,
                    "tf_width": pl.tf_width,
                    "tf_height": pl.tf_height,
                    "tf_dimension_unit": pl.tf_dimension_unit,
                    "tf_weight": pl.tf_weight,
                    "tf_weight_unit": pl.tf_weight_unit,
                    "tf_storage_rate": pl.tf_storage_rate,
                    "tf_location_note": pl.tf_location_note,
                }))

            # AUTO-GENERATE missing serial lines right when the wizard opens
            # (so user doesn't have to click "Generate Serials")
            if sol.product_id.tracking == "serial":
                target = int(sol.product_uom_qty or 0)
                if target > 0:
                    existing = len(lines)
                    for i in range(existing, target):
                        name = self.env["ir.sequence"].next_by_code("stock.lot.serial") \
                               or self.env["ir.sequence"].next_by_code("stock.lot")
                        if not name:
                            raise UserError(_("No serial sequence found. Please configure a sequence for code 'stock.lot.serial'."))
                        lines.append((0, 0, {
                            "sequence": (i + 1) * 10,
                            "serial_name": name,
                        }))

            res["line_ids"] = lines
        return res

    def _next_serial(self):
        # Use the existing Odoo serial sequence if present
        name = self.env["ir.sequence"].next_by_code("stock.lot.serial")
        if not name:
            # fallback - still system-generated (but you can adjust later if needed)
            name = self.env["ir.sequence"].next_by_code("stock.lot")
        if not name:
            raise UserError(_("No serial sequence found. Please configure a sequence for code 'stock.lot.serial'."))
        return name

    def action_generate_serials(self):
        self.ensure_one()
        if self.product_id.tracking != "serial":
            raise UserError(_("This product is not tracked by unique serial number."))

        target = int(self.qty)
        existing = len(self.line_ids)

        if target <= 0:
            raise UserError(_("Quantity must be > 0 to generate serials."))

        # Add missing lines
        for i in range(existing, target):
            self.line_ids = [(0, 0, {"sequence": (i + 1) * 10, "serial_name": self._next_serial()})]

        # If too many lines, do not auto-delete (safer); user can remove manually
        return {
            "type": "ir.actions.act_window",
            "res_model": "tf.sale.serial.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()

        if self.product_id.tracking != "serial":
            raise UserError(_("This product is not tracked by unique serial number."))

        target = int(self.qty)
        if len(self.line_ids) != target:
            raise UserError(_("You must have exactly %s serial lines (same as quantity).") % target)

        # Replace plan lines with wizard content
        self.order_line_id.tf_serial_plan_ids.unlink()

        vals_list = []
        for wl in self.line_ids.sorted(lambda x: x.sequence):
            if not wl.serial_name:
                raise UserError(_("Serial Number cannot be empty."))
            vals_list.append({
                "order_id": self.order_id.id,
                "order_line_id": self.order_line_id.id,
                "sequence": wl.sequence,
                "serial_name": wl.serial_name,
                "tf_description": wl.tf_description,
                "tf_length": wl.tf_length,
                "tf_width": wl.tf_width,
                "tf_height": wl.tf_height,
                "tf_dimension_unit": wl.tf_dimension_unit,
                "tf_weight": wl.tf_weight,
                "tf_weight_unit": wl.tf_weight_unit,
                "tf_storage_rate": wl.tf_storage_rate,
                "tf_location_note": wl.tf_location_note,
            })

        self.env["tf.sale.serial.plan"].create(vals_list)
        return {"type": "ir.actions.act_window_close"}


class TfSaleSerialWizardLine(models.TransientModel):
    _name = "tf.sale.serial.wizard.line"
    _description = "TF Sale Serial Wizard Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("tf.sale.serial.wizard", required=True, ondelete="cascade")

    sequence = fields.Integer(default=10)
    serial_name = fields.Char(string="Serial Number", required=True)
    tf_description = fields.Char(string="Description")

    tf_length = fields.Float(string="Length")
    tf_width = fields.Float(string="Width")
    tf_height = fields.Float(string="Height")
    tf_dimension_unit = fields.Selection(
        [("mm", "mm"), ("cm", "cm"), ("m", "m"), ("in", "in"), ("ft", "ft")],
        string="Dim Unit",
    )
    tf_weight = fields.Float(string="Weight")
    tf_weight_unit = fields.Selection(
        [("g", "g"), ("kg", "kg"), ("lb", "lb")],
        string="Weight Unit",
    )
    tf_storage_rate = fields.Selection(
        [("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        string="Storage Rate",
    )
    tf_location_note = fields.Char(string="Location (Text)")
