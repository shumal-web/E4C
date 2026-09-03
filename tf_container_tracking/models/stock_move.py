# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _tf_format_m2o_for_web(self, field_name, record):
        if not record:
            return False
        return {
            "id": record.id,
            "display_name": record.display_name,
        }

    def tf_get_generate_serial_dialog_defaults(self):
        self.ensure_one()
        template_lines = self.move_line_ids.sorted(lambda ml: ml.id)
        sample_line = template_lines[:1]
        sample_source = sample_line.lot_id or sample_line.tf_sale_serial_plan_id or sample_line
        container_plan = (
            sample_line.tf_container_plan_id
            or sample_line.tf_sale_serial_plan_id.tf_container_plan_id
            or self.picking_id.tf_container_plan_id
        )
        prefix = False
        if container_plan:
            prefix = container_plan.serial_name or container_plan.tf_container_number or False
            if prefix and not prefix.endswith("/"):
                prefix = "%s/" % prefix
        product_template = self.product_id.product_tmpl_id
        dimension_unit = sample_source.tf_dimension_unit or False
        weight_unit = sample_source.tf_weight_unit or False
        if self.product_id.tracking == "serial":
            if product_template.tf_is_container:
                weight_unit = weight_unit or "kg"
            elif not product_template.tf_direct_container_to_client and not product_template.tf_cfs_pieces_flow:
                dimension_unit = dimension_unit or "cm"
                weight_unit = weight_unit or "kg"
        return {
            "first_serial": ("%s001" % prefix) if prefix else False,
            "tf_length": sample_source.tf_length or 0.0,
            "tf_width": sample_source.tf_width or 0.0,
            "tf_height": sample_source.tf_height or 0.0,
            "tf_dimension_unit": dimension_unit,
            "tf_weight": sample_source.tf_weight or 0.0,
            "tf_weight_unit": weight_unit,
            "template_move_line_ids": template_lines.ids,
        }

    def action_generate_lot_line_vals(self, context_data, mode, first_lot, count, lot_text):
        vals_list = super().action_generate_lot_line_vals(context_data, mode, first_lot, count, lot_text)

        template_line_ids = context_data.get("default_tf_template_move_line_ids") or []
        template_lines = self.env["stock.move.line"].browse(template_line_ids).exists().sorted(lambda ml: ml.id)
        attrs = {
            "tf_length": context_data.get("default_tf_length"),
            "tf_width": context_data.get("default_tf_width"),
            "tf_height": context_data.get("default_tf_height"),
            "tf_dimension_unit": context_data.get("default_tf_dimension_unit"),
            "tf_weight": context_data.get("default_tf_weight"),
            "tf_weight_unit": context_data.get("default_tf_weight_unit"),
        }

        for index, values in enumerate(vals_list):
            template_line = template_lines[index:index + 1] or template_lines[:1]
            if template_line:
                template_line = template_line[0]
                if template_line.tf_sale_serial_plan_id:
                    values["tf_sale_serial_plan_id"] = self._tf_format_m2o_for_web(
                        "tf_sale_serial_plan_id", template_line.tf_sale_serial_plan_id
                    )
                if template_line.tf_container_plan_id:
                    values["tf_container_plan_id"] = self._tf_format_m2o_for_web(
                        "tf_container_plan_id", template_line.tf_container_plan_id
                    )
                if not values.get("tf_description"):
                    values["tf_description"] = template_line.tf_description
                if not values.get("tf_storage_rate"):
                    values["tf_storage_rate"] = template_line.tf_storage_rate
                if not values.get("tf_location_note"):
                    values["tf_location_note"] = template_line.tf_location_note
            for key, value in attrs.items():
                values[key] = value
        return vals_list
