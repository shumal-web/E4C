# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .sale_serial_plan import INTERNAL_STATUS_SELECTION, CONTAINER_STATUS_SELECTION


SERIAL_ATTRIBUTE_FIELDS = {
    "tf_description",
    "tf_length",
    "tf_width",
    "tf_height",
    "tf_dimension_unit",
    "tf_weight",
    "tf_weight_unit",
    "tf_storage_rate",
    "tf_location_note",
}

CONTAINER_ATTRIBUTE_FIELDS = {
    "tf_internal_status",
    "tf_port_to_destuff",
    "tf_container_status",
    "tf_container_location",
    "tf_eta",
    "tf_lfd",
    "tf_ssl",
    "tf_container_type",
    "tf_chassis_no",
    "tf_pubk_no",
}


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    tf_is_container_product = fields.Boolean(
        related="product_id.product_tmpl_id.tf_is_container",
        readonly=True,
    )

    tf_container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Serial",
        index=True,
    )

    tf_internal_status = fields.Selection(
        INTERNAL_STATUS_SELECTION,
        string="Internal Status",
        default="for_approval",
    )
    tf_port_to_destuff = fields.Char(string="Port to De-stuff")
    tf_container_status = fields.Selection(
        CONTAINER_STATUS_SELECTION,
        string="Container Status",
        default="on_water",
    )
    tf_container_location = fields.Char(string="Container Location")
    tf_eta = fields.Date(string="ETA")
    tf_lfd = fields.Date(string="LFD")
    tf_ssl = fields.Char(string="SSL")
    tf_container_type = fields.Char(string="Type")
    tf_chassis_no = fields.Char(string="Chassis #")
    tf_pubk_no = fields.Char(string="PU/BK #")

    tf_allowed_lot_ids = fields.Many2many(
        "stock.lot",
        compute="_compute_tf_allowed_lot_ids",
        string="Allowed Serials",
        compute_sudo=True,
    )
    tf_hide_container_columns = fields.Boolean(
        compute="_compute_tf_hide_container_columns",
        string="Hide Container Columns",
    )

    @api.depends(
        "product_id",
        "location_id",
        "picking_id.location_id",
        "picking_id.tf_sale_order_id",
        "picking_id.picking_type_code",
        "tf_sale_serial_plan_id",
    )
    def _compute_tf_allowed_lot_ids(self):
        Quant = self.env["stock.quant"]
        for line in self:
            line.tf_allowed_lot_ids = self.env["stock.lot"]
            if not line.product_id or not line.picking_id or line.product_id.tracking != "serial":
                continue
            if line.tf_sale_serial_plan_id and line.tf_sale_serial_plan_id.lot_id:
                line.tf_allowed_lot_ids = line.tf_sale_serial_plan_id.lot_id
                continue
            source_location = line.location_id or line.picking_id.location_id
            if not source_location:
                continue

            quant_domain = [
                ("product_id", "=", line.product_id.id),
                ("lot_id", "!=", False),
                ("location_id", "child_of", source_location.id),
                ("location_id.usage", "in", ["internal", "transit"]),
                ("quantity", ">", 0),
            ]
            quants = Quant.search(quant_domain)
            available_by_lot = {}
            for quant in quants:
                lot = quant.lot_id
                if not lot:
                    continue
                available_by_lot.setdefault(lot.id, 0.0)
                available_by_lot[lot.id] += quant.quantity

            lot_ids = [lot_id for lot_id, qty in available_by_lot.items() if qty > 0]
            if line.picking_id.picking_type_code == "internal" and line.picking_id.tf_sale_order_id:
                lots = self.env["stock.lot"].search(
                    [
                        ("id", "in", lot_ids),
                        ("tf_origin_sale_order_id", "=", line.picking_id.tf_sale_order_id.id),
                    ]
                )
                lot_ids = lots.ids
            line.tf_allowed_lot_ids = self.env["stock.lot"].browse(lot_ids)

    @api.depends("picking_id.picking_type_code", "tf_is_container_product")
    def _compute_tf_hide_container_columns(self):
        for line in self:
            line.tf_hide_container_columns = bool(
                line.picking_id
                and line.picking_id.picking_type_code == "incoming"
                and not line.tf_is_container_product
            )

    @api.depends("picking_id.picking_type_code", "picking_id.state")
    def _compute_tf_allow_receipt_edit(self):
        for line in self:
            line.tf_allow_receipt_edit = bool(
                line.picking_id
                and line.picking_id.picking_type_code == "incoming"
                and line.picking_id.state != "cancel"
            )

    def write(self, vals):
        sync_fields = (SERIAL_ATTRIBUTE_FIELDS | CONTAINER_ATTRIBUTE_FIELDS | {"tf_container_plan_id"}).intersection(vals)
        res = super().write(vals)
        if sync_fields:
            self._tf_sync_done_receipt_attribute_edits(sync_fields)
        return res

    def _tf_sync_done_receipt_attribute_edits(self, changed_fields):
        done_receipt_lines = self.filtered(
            lambda line: line.picking_id.picking_type_code == "incoming"
            and line.picking_id.state == "done"
            and line.product_id.tracking == "serial"
        )
        for line in done_receipt_lines:
            lot = line.lot_id
            serial_plan = line.tf_sale_serial_plan_id
            if not serial_plan and lot:
                serial_plan = self.env["tf.sale.serial.plan"].search([("lot_id", "=", lot.id)], limit=1)

            lot_vals = {
                field_name: getattr(line, field_name)
                for field_name in changed_fields
                if lot and field_name in lot._fields
            }
            if lot_vals:
                lot.write(lot_vals)

            plan_vals = {
                field_name: getattr(line, field_name)
                for field_name in changed_fields
                if serial_plan and field_name in serial_plan._fields
            }
            if plan_vals:
                serial_plan.write(plan_vals)

            if "tf_container_plan_id" in changed_fields and serial_plan and not serial_plan.tf_is_container_product:
                serial_plan.tf_container_plan_id = line.tf_container_plan_id.id or False
                if lot and line.tf_container_plan_id and line.tf_container_plan_id.lot_id:
                    lot.tf_container_lot_id = line.tf_container_plan_id.lot_id.id
