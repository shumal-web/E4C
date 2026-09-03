# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .report_helpers import (
    container_plan_label,
    dimension_text,
    format_date,
    format_datetime,
    format_quantity,
    move_line_container_label,
    move_line_serial_name,
    move_line_source,
    partner_address,
    safe_get,
    selection_label,
    text_value,
    weight_text,
)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def action_e4c_print_receiving_labels(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_receiving_labels").with_context(
            discard_logo_check=True
        ).report_action(self)

    def action_e4c_print_truck_in_sheet(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_truck_in_sheet").with_context(
            discard_logo_check=True
        ).report_action(self)

    def action_e4c_print_truck_out_sheet(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_truck_out_sheet_picking").with_context(
            discard_logo_check=True
        ).report_action(self)

    def _e4c_report_sale_orders(self):
        self.ensure_one()
        sale_orders = self.env["sale.order"]
        if safe_get(self, "tf_sale_order_id"):
            sale_orders |= self.tf_sale_order_id
        if "sale_id" in self._fields and self.sale_id:
            sale_orders |= self.sale_id
        sale_orders |= self.move_ids.sale_line_id.order_id
        if not sale_orders and self.origin:
            names = [part.strip() for part in self.origin.split(",") if part.strip()]
            if names:
                sale_orders = self.env["sale.order"].search([("name", "in", names)])
        return sale_orders

    def _e4c_report_sale_order_name(self):
        self.ensure_one()
        names = self._e4c_report_sale_orders().mapped("name")
        return ", ".join(names) or text_value(self.origin)

    def _e4c_report_customer(self):
        self.ensure_one()
        sale_orders = self._e4c_report_sale_orders()
        return self.partner_id or sale_orders[:1].partner_id

    def _e4c_report_customer_name(self):
        self.ensure_one()
        customer = self._e4c_report_customer()
        return customer.display_name if customer else ""

    def _e4c_report_customer_address(self):
        self.ensure_one()
        return self._e4c_report_consignee_address()

    def _e4c_report_shipper_address(self):
        self.ensure_one()
        sale_order = self._e4c_report_sale_orders()[:1]
        return text_value(safe_get(sale_order, "tf_shipper_note")) or "E4C\n795 GEORGE V\nLACHINE,QC H8S 3K3"

    def _e4c_report_consignee_address(self):
        self.ensure_one()
        sale_order = self._e4c_report_sale_orders()[:1]
        return (
            text_value(safe_get(sale_order, "tf_consignee_note"))
            or text_value(safe_get(sale_order, "tf_address_note"))
            or partner_address(self.partner_id or sale_order.partner_shipping_id or sale_order.partner_id)
        )

    def _e4c_report_customer_reference(self):
        self.ensure_one()
        sale_order = self._e4c_report_sale_orders()[:1]
        return text_value(sale_order.client_order_ref if sale_order else False)

    def _e4c_report_special_instructions(self):
        self.ensure_one()
        sale_order = self._e4c_report_sale_orders()[:1]
        return text_value(safe_get(self, "tf_special_instructions") or safe_get(sale_order, "tf_special_instructions"))

    def _e4c_report_tags(self):
        self.ensure_one()
        sale_order = self._e4c_report_sale_orders()[:1]
        tags = safe_get(self, "tf_sale_tag_ids")
        if not tags and sale_order and "tag_ids" in sale_order._fields:
            tags = sale_order.tag_ids
        return ", ".join(tags.mapped("name")) if tags else ""

    def _e4c_report_date(self):
        self.ensure_one()
        return format_date(self, self.scheduled_date or safe_get(self, "date_deadline") or self.create_date)

    def _e4c_report_datetime(self):
        self.ensure_one()
        return format_datetime(self, self.scheduled_date or safe_get(self, "date_deadline") or self.create_date)

    def _e4c_report_container_number(self):
        self.ensure_one()
        container_plan = safe_get(self, "tf_container_plan_id")
        if container_plan:
            return container_plan_label(container_plan)
        for move_line in self.move_line_ids:
            label = move_line_container_label(move_line)
            if label:
                return label
        return text_value(safe_get(self, "tf_container_number"))

    def _e4c_report_flow_label(self):
        self.ensure_one()
        return selection_label(self, "tf_flow_kind", safe_get(self, "tf_flow_kind"))

    def _e4c_report_source_location(self):
        self.ensure_one()
        return self.location_id.display_name or ""

    def _e4c_report_destination_location(self):
        self.ensure_one()
        return self.location_dest_id.display_name or self.partner_id.display_name or ""

    def _e4c_report_carrier(self):
        self.ensure_one()
        carrier = safe_get(self, "carrier_id")
        return text_value(carrier.display_name if carrier else "")

    def _e4c_report_driver(self):
        self.ensure_one()
        return ""

    def _e4c_report_truck(self):
        self.ensure_one()
        return ""

    def _e4c_report_trailer(self):
        self.ensure_one()
        return ""

    def _e4c_report_line_values(self):
        self.ensure_one()
        values = []
        for index, move_line in enumerate(self.move_line_ids.sorted(lambda ml: (ml.move_id.sequence or 0, ml.id)), start=1):
            source = move_line_source(move_line)
            values.append({
                "index": index,
                "product": move_line.product_id.display_name,
                "quantity": format_quantity(move_line.quantity or 1.0),
                "unit": move_line.product_uom_id.name or "",
                "serial": move_line_serial_name(move_line),
                "container": move_line_container_label(move_line),
                "description": text_value(safe_get(source, "tf_description") or move_line.move_id.description_picking or move_line.product_id.display_name),
                "dimensions": dimension_text(source),
                "length": safe_get(source, "tf_length") or 0.0,
                "width": safe_get(source, "tf_width") or 0.0,
                "height": safe_get(source, "tf_height") or 0.0,
                "dimension_unit": text_value(safe_get(source, "tf_dimension_unit")),
                "weight": weight_text(source),
                "weight_value": safe_get(source, "tf_weight") or 0.0,
                "weight_unit": text_value(safe_get(source, "tf_weight_unit")),
                "location": text_value(safe_get(source, "tf_location_note") or move_line.location_id.display_name),
                "condition": "",
                "pictures": "",
            })
        if values:
            return values

        for index, move in enumerate(self.move_ids.sorted(lambda move: (move.sequence or 0, move.id)), start=1):
            values.append({
                "index": index,
                "product": move.product_id.display_name,
                "quantity": format_quantity(move.product_uom_qty),
                "unit": move.product_uom.name or "",
                "serial": "",
                "container": self._e4c_report_container_number(),
                "description": text_value(move.description_picking or move.product_id.display_name),
                "dimensions": "",
                "length": 0.0,
                "width": 0.0,
                "height": 0.0,
                "dimension_unit": "",
                "weight": "",
                "weight_value": 0.0,
                "weight_unit": "",
                "location": self.location_id.display_name or "",
                "condition": "",
                "pictures": "",
            })
        return values

    def _e4c_report_label_values(self):
        self.ensure_one()
        labels = []
        lines = self._e4c_report_line_values()
        total = len(lines) or 1
        for index, line in enumerate(lines, start=1):
            labels.append({
                "sales_order": self._e4c_report_sale_order_name(),
                "customer": self._e4c_report_customer_name(),
                "date": self._e4c_report_date(),
                "container": line.get("container") or self._e4c_report_container_number(),
                "serial": line.get("serial"),
                "description": line.get("description") or line.get("product"),
                "piece_index": index,
                "piece_total": total,
            })
        return labels or [{
            "sales_order": self._e4c_report_sale_order_name(),
            "customer": self._e4c_report_customer_name(),
            "date": self._e4c_report_date(),
            "container": self._e4c_report_container_number(),
            "serial": self.name,
            "description": self._e4c_report_flow_label() or self.picking_type_id.display_name,
            "piece_index": 1,
            "piece_total": 1,
        }]
