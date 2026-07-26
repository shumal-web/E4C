# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TfSaleSerialPlan(models.Model):
    _name = "tf.sale.serial.plan"
    _description = "TF Sale Serial Plan Line"
    _order = "sequence, id"

    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", index=True)
    order_line_id = fields.Many2one("sale.order.line", required=True, ondelete="cascade", index=True)

    sequence = fields.Integer(default=10)
    product_id = fields.Many2one(related="order_line_id.product_id", store=True, readonly=True)
    company_id = fields.Many2one(related="order_id.company_id", store=True, readonly=True)

    serial_name = fields.Char(string="Serial Number", required=True, index=True)
    tf_description = fields.Char(string="Description")

    # Attributes (can be blank)
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

    # Link to actual lot once received
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial", readonly=True)
