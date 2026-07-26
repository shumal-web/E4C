# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockLot(models.Model):
    _inherit = "stock.lot"

    # Stored attributes on the real serial
    tf_description = fields.Char(string="Piece Description")
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

    tf_reception_date = fields.Date(string="Reception Date")
    tf_delivery_date = fields.Date(string="Delivery Date")

    tf_day_counter = fields.Char(
        string="Day Counter (Days in WH)",
        compute="_compute_tf_day_counter",
        store=False,
    )

    @api.depends("tf_reception_date", "tf_delivery_date")
    def _compute_tf_day_counter(self):
        today = fields.Date.context_today(self)
        for lot in self:
            if not lot.tf_reception_date:
                lot.tf_day_counter = ""
                continue
            end = lot.tf_delivery_date or today
            lot.tf_day_counter = str((end - lot.tf_reception_date).days)
