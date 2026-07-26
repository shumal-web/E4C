# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    tf_sale_serial_plan_id = fields.Many2one("tf.sale.serial.plan", string="Serial Plan Line", index=True)

    # Copy of attributes for editing on receipt before validation
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

    tf_allow_receipt_edit = fields.Boolean(
        compute="_compute_tf_allow_receipt_edit",
        string="Allow Receipt Edit",
    )

    @api.depends("picking_id.picking_type_code", "picking_id.state")
    def _compute_tf_allow_receipt_edit(self):
        for ml in self:
            ml.tf_allow_receipt_edit = bool(
                ml.picking_id
                and ml.picking_id.picking_type_code == "incoming"
                and ml.picking_id.state not in ("done", "cancel")
            )
