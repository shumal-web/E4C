# -*- coding: utf-8 -*-
from odoo import fields, models

from .report_helpers import (
    container_plan_label,
    dimension_text,
    format_date,
    format_datetime,
    format_quantity,
    partner_address,
    safe_get,
    selection_label,
    text_value,
    weight_text,
)


BOL_TERMS = """
Unless Declared Value Maximum liability for transportation is $2.00 per pound or $4.41 per kilo.

APPLICATION
The following applies to transportation of goods by for-hire highway carrier licensed under the Motor Vehicle Transport Act or under provincial statutes, except for excluded commodities such as used household goods, livestock, bus parcel express shipments, personal luggage of bus passengers, and other specific commodities excluded by law.

BILL OF LADING
1. A Bill of Lading shall be completed for each shipment.
2. Each article covered by the Bill of Lading shall be marked by the consignor with the name of the consignee and destination, except where the shipment is one truckload from one consignor to one consignee.
3. The Bill of Lading shall be signed in full by the consignor and the carrier as acceptance of all terms and conditions.
4. A waybill may be prepared by the carrier and shall carry the same number or identification as the original Bill of Lading. The waybill does not replace the original Bill of Lading.

CONDITIONS OF CARRIAGE
1. The carrier is liable for loss or damage to goods accepted by the carrier or its agent except as provided in these conditions.
2. Where more than one carrier handles the shipment, the originating and delivering carriers are liable for loss or damage while goods are in the custody of another carrier unless relieved by law.
3. The originating or delivering carrier may recover from another carrier the amount paid for loss or damage caused while goods were in that carrier's custody.
4. Nothing in these conditions removes rights the consignor or consignee may have against any carrier.
5. The carrier is not liable for loss, damage or delay caused by an Act of God, public enemies, riots, strikes, inherent defect in the goods, act or default of consignor, owner or consignee, authority of law, quarantine, or natural shrinkage.
6. No carrier is bound to transport goods by a particular vehicle or by a particular time unless agreed on the Bill of Lading and signed by the parties.
7. If goods must be forwarded by another conveyance because of physical necessity, the carrier liability remains the same as if moved by licensed for-hire vehicle.
8. Goods stopped and held in transit at the request of the party entitled to request it are held at that party's risk.
9. Loss or damage liability is based on the value of the goods at the place and time of shipment, including freight and other charges if paid, or any lower value agreed in writing.
10. Unless a higher value is declared on the Bill of Lading, maximum liability shall not exceed $4.41 per kilogram computed on the total shipment weight.
11. If goods are carried at consignor's risk, the agreement covers only risks necessarily incidental to transportation and does not relieve the carrier from negligent loss, damage or delay.
12. Notice of claim for loss, damage or delay must be given in writing within sixty days after delivery, or within nine months from shipment date if delivery fails. The final claim statement must be filed within nine months from shipment date with a copy of the paid freight bill.
13. The carrier is not bound to carry documents, specie or articles of extraordinary value unless a special agreement is made. If such goods are carried without disclosure, liability is limited to the maximum liability stated above.
14. Freight and other lawful charges may be required before delivery. If the goods are not as described, charges apply to the goods actually shipped. Shipments move collect unless prepaid is indicated.
15. Anyone shipping dangerous goods without full legal disclosure must indemnify the carrier against loss, damage or delay, and such goods may be warehoused at consignor's risk and expense.
16. If goods cannot be delivered through no fault of the carrier, the carrier shall notify the consignor and consignee and request disposal instructions. Pending instructions, goods may be stored subject to lawful charges.
17. If no disposal instructions are received within ten days after notice, the carrier may return undelivered goods to the consignor at consignor's expense.
18. Alterations, additions or erasures to the Bill of Lading must be signed or initialed by the consignor or agent and the originating carrier or agent.
19. The consignor is responsible for correct shipping weights. If actual weight differs from the Bill of Lading, the carrier may correct it.
20. C.O.D. shipments must not be delivered unless payment is received in full. C.O.D. charges and remittance must follow applicable carrier rules.
""".strip()


class TfDispatchTicket(models.Model):
    _inherit = "tf.dispatch.ticket"

    def action_e4c_print_bol(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_dispatch_bol").with_context(
            discard_logo_check=True
        ).report_action(self)

    def action_e4c_print_truck_out_sheet(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_dispatch_truck_out_sheet").with_context(
            discard_logo_check=True
        ).report_action(self)

    def action_e4c_print_export_checklist(self):
        return self.env.ref("tf_e4c_printouts.action_report_e4c_export_checklist").with_context(
            discard_logo_check=True
        ).report_action(self)

    def _e4c_report_sale_orders(self):
        self.ensure_one()
        return self.sale_order_ids or self.sale_order_id

    def _e4c_report_sale_order_name(self):
        self.ensure_one()
        return ", ".join(self._e4c_report_sale_orders().mapped("name")) or text_value(self.sale_order_id.name)

    def _e4c_report_customer(self):
        self.ensure_one()
        return self.customer_id or self.sale_order_id.partner_id

    def _e4c_report_customer_name(self):
        self.ensure_one()
        customer = self._e4c_report_customer()
        return customer.display_name if customer else ""

    def _e4c_report_customer_address(self):
        self.ensure_one()
        return self._e4c_report_consignee_address()

    def _e4c_report_shipper_address(self):
        self.ensure_one()
        sale_order = self.sale_order_id
        return text_value(safe_get(sale_order, "tf_shipper_note")) or "E4C\n795 GEORGE V\nLACHINE,QC H8S 3K3"

    def _e4c_report_consignee_address(self):
        self.ensure_one()
        sale_order = self.sale_order_id
        return (
            text_value(safe_get(sale_order, "tf_consignee_note"))
            or text_value(safe_get(sale_order, "tf_address_note"))
            or partner_address(sale_order.partner_shipping_id or sale_order.partner_id)
        )

    def _e4c_report_customer_reference(self):
        self.ensure_one()
        return text_value(self.customer_reference or self.sale_order_id.client_order_ref)

    def _e4c_report_special_instructions(self):
        self.ensure_one()
        return text_value(safe_get(self, "tf_special_instructions") or safe_get(self.sale_order_id, "tf_special_instructions"))

    def _e4c_report_tags(self):
        self.ensure_one()
        tags = safe_get(self, "tf_sale_tag_ids")
        if not tags and self.sale_order_id and "tag_ids" in self.sale_order_id._fields:
            tags = self.sale_order_id.tag_ids
        return ", ".join(tags.mapped("name")) if tags else ""

    def _e4c_report_date(self):
        self.ensure_one()
        return format_date(self, self.dispatch_date or self.create_date)

    def _e4c_report_datetime(self):
        self.ensure_one()
        return format_datetime(self, self.dispatch_date or self.create_date)

    def _e4c_report_container_number(self):
        self.ensure_one()
        return text_value(self.container_number) or container_plan_label(self.container_plan_id)

    def _e4c_report_dispatch_type_label(self):
        self.ensure_one()
        return selection_label(self, "dispatch_type", self.dispatch_type)

    def _e4c_report_source_location(self):
        self.ensure_one()
        picking = self.internal_transfer_id or self.delivery_order_id or self.receiving_picking_id
        if picking:
            return picking.location_id.display_name or ""
        return text_value(self.location_note or self.location_partner_id.display_name)

    def _e4c_report_destination_location(self):
        self.ensure_one()
        picking = self.delivery_order_id or self.internal_transfer_id or self.receiving_picking_id
        if picking:
            return picking.location_dest_id.display_name or picking.partner_id.display_name or ""
        return text_value(self.trailer_destination_location or self.location_note or self.location_partner_id.display_name)

    def _e4c_report_carrier(self):
        self.ensure_one()
        return text_value(self.truck_id.display_name or self.trailer_id.display_name)

    def _e4c_report_driver(self):
        self.ensure_one()
        return text_value(self.driver_id.display_name)

    def _e4c_report_truck(self):
        self.ensure_one()
        return text_value(self.truck_id.display_name)

    def _e4c_report_trailer(self):
        self.ensure_one()
        return text_value(self.trailer_id.display_name)

    def _e4c_report_primary_picking(self):
        self.ensure_one()
        return self.delivery_order_id or self.internal_transfer_id or self.receiving_picking_id

    def _e4c_report_line_values(self):
        self.ensure_one()
        picking = self._e4c_report_primary_picking()
        if picking:
            return picking._e4c_report_line_values()

        values = []
        piece_plans = self.container_plan_id.tf_piece_plan_ids.filtered(lambda plan: not plan.tf_is_container_product)
        for index, plan in enumerate(piece_plans.sorted(lambda line: (line.sequence or 0, line.id)), start=1):
            source = plan.lot_id or plan
            values.append({
                "index": index,
                "product": plan.product_id.display_name,
                "quantity": "1",
                "unit": plan.product_id.uom_id.name or "",
                "serial": text_value(plan.serial_name),
                "container": self._e4c_report_container_number(),
                "description": text_value(safe_get(source, "tf_description") or plan.product_id.display_name),
                "dimensions": dimension_text(source),
                "length": safe_get(source, "tf_length") or 0.0,
                "width": safe_get(source, "tf_width") or 0.0,
                "height": safe_get(source, "tf_height") or 0.0,
                "dimension_unit": text_value(safe_get(source, "tf_dimension_unit")),
                "weight": weight_text(source),
                "weight_value": safe_get(source, "tf_weight") or 0.0,
                "weight_unit": text_value(safe_get(source, "tf_weight_unit")),
                "location": text_value(safe_get(source, "tf_location_note")),
                "condition": "",
                "pictures": "",
            })
        if values:
            return values

        plan = self.container_plan_id
        if plan:
            return [{
                "index": 1,
                "product": plan.product_id.display_name,
                "quantity": format_quantity(1.0),
                "unit": plan.product_id.uom_id.name or "",
                "serial": text_value(plan.serial_name),
                "container": self._e4c_report_container_number(),
                "description": text_value(safe_get(plan, "tf_description") or plan.product_id.display_name),
                "dimensions": dimension_text(plan),
                "length": safe_get(plan, "tf_length") or 0.0,
                "width": safe_get(plan, "tf_width") or 0.0,
                "height": safe_get(plan, "tf_height") or 0.0,
                "dimension_unit": text_value(safe_get(plan, "tf_dimension_unit")),
                "weight": weight_text(plan),
                "weight_value": safe_get(plan, "tf_weight") or 0.0,
                "weight_unit": text_value(safe_get(plan, "tf_weight_unit")),
                "location": text_value(safe_get(plan, "tf_location_note")),
                "condition": "",
                "pictures": "",
            }]
        return []

    def _e4c_report_total_pieces(self):
        self.ensure_one()
        total = 0.0
        for line in self._e4c_report_line_values():
            try:
                total += float(line.get("quantity") or 0.0)
            except (TypeError, ValueError):
                continue
        return format_quantity(total)

    def _e4c_report_total_weight(self):
        self.ensure_one()
        total = 0.0
        units = set()
        for line in self._e4c_report_line_values():
            total += float(line.get("weight_value") or 0.0)
            if line.get("weight_unit"):
                units.add(line["weight_unit"])
        if not total:
            return ""
        unit = units.pop() if len(units) == 1 else ""
        return "%s %s" % (format_quantity(total), unit) if unit else format_quantity(total)

    def _e4c_report_bol_terms(self):
        self.ensure_one()
        return BOL_TERMS
