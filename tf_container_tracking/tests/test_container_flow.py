# -*- coding: utf-8 -*-
from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.tests.common import TransactionCase
from odoo.exceptions import AccessError, UserError, ValidationError


class TestContainerFlow(TransactionCase):
    def _create_partner(self, name):
        return self.env["res.partner"].create({"name": name})

    def _create_product(self, name, is_container=False, requires_container=False):
        template = self.env["product.template"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "tf_is_container": is_container,
            "tf_requires_container": requires_container,
            "sale_ok": True,
            "purchase_ok": True,
            "list_price": 1.0,
        })
        return template.product_variant_id

    def _create_so_line(self, order, product, qty):
        return self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": product.id,
            "product_uom_qty": qty,
            "product_uom_id": product.uom_id.id,
            "price_unit": 1.0,
            "name": product.display_name,
        })

    def _open_wizard(self, order_line):
        return self.env["tf.sale.serial.wizard"].with_context(default_order_line_id=order_line.id).create({})

    def _validate_picking(self, picking):
        result = picking.button_validate()
        if isinstance(result, dict):
            model = result.get("res_model")
            res_id = result.get("res_id")
            if model == "stock.immediate.transfer" and res_id:
                self.env[model].browse(res_id).process()
            elif model == "stock.backorder.confirmation" and res_id:
                self.env[model].browse(res_id).process()

    def _receive_sale_lines(self, sale_order, sale_lines):
        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(incoming_type, "Incoming picking type is required for this test.")

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": sale_order.partner_id.id,
            "origin": sale_order.name,
            "tf_sale_order_id": sale_order.id,
        })
        for line in sale_lines:
            self.env["stock.move"].create({
                "description_picking": line.product_id.display_name,
                "picking_id": picking.id,
                "product_id": line.product_id.id,
                "product_uom": line.product_uom_id.id,
                "product_uom_qty": line.product_uom_qty,
                "location_id": incoming_type.default_location_src_id.id,
                "location_dest_id": incoming_type.default_location_dest_id.id,
                "sale_line_id": line.id,
            })

        picking.action_confirm()
        picking._tf_prefill_incoming_from_sale_serial_plan()
        for index, move_line in enumerate(picking.move_line_ids.sorted(lambda ml: ml.id), start=1):
            move_line.lot_name = move_line.lot_name or f"RCV-LOT-{index}"
            move_line.quantity = 1.0
        self._validate_picking(picking)
        return picking

    def test_sales_order_dispatch_fields_exist_and_view_loads(self):
        sale_model = self.env["sale.order"]
        self.assertIn("tf_container_tracking_count", sale_model._fields)
        self.assertIn("tf_dispatch_ticket_count", sale_model._fields)
        self.assertIn("tf_shipment_type", sale_model._fields)
        self.assertIn("tf_flow_state", sale_model._fields)
        self.assertIn("tf_address_note", sale_model._fields)
        self.assertIn("tf_special_instructions", sale_model._fields)
        self.assertIn("tf_credit_state", sale_model._fields)
        self.assertIn("tf_partner_credit_limit", sale_model._fields)
        self.assertIn("tf_shipment_type", self.env["sale.order.template"]._fields)
        self.assertIn("tf_direct_container_to_client", self.env["product.template"]._fields)
        self.assertIn("tf_credit_limit", self.env["res.partner"]._fields)
        self.assertIn("tf_credit_used", self.env["res.partner"]._fields)

        form_view = sale_model.get_view(
            view_id=self.env.ref("sale.view_order_form").id,
            view_type="form",
        )
        self.assertIn("tf_container_tracking_count", form_view["arch"])
        self.assertIn("tf_dispatch_ticket_count", form_view["arch"])
        self.assertIn("tf_shipment_type", form_view["arch"])
        self.assertIn("tf_flow_state", form_view["arch"])
        self.assertIn("tf_address_note", form_view["arch"])
        self.assertIn("tf_special_instructions", form_view["arch"])
        self.assertIn("tf_credit_state", form_view["arch"])
        self.assertIn("tf_partner_credit_limit", form_view["arch"])
        self.assertIn("client_order_ref", form_view["arch"])
        self.assertIn('open_attachments="True"', form_view["arch"])

        sale_order_fields = form_view["models"]["sale.order"]
        self.assertIn("tf_container_tracking_count", sale_order_fields)
        self.assertIn("tf_dispatch_ticket_count", sale_order_fields)
        self.assertIn("tf_shipment_type", sale_order_fields)
        self.assertIn("tf_flow_state", sale_order_fields)
        self.assertIn("tf_address_note", sale_order_fields)
        self.assertIn("tf_special_instructions", sale_order_fields)
        self.assertIn("tf_credit_state", sale_order_fields)
        self.assertIn("tf_partner_credit_limit", sale_order_fields)

        partner_view = self.env["res.partner"].get_view(
            view_id=self.env.ref("base.view_partner_form").id,
            view_type="form",
        )
        self.assertIn("tf_credit_limit", partner_view["arch"])
        self.assertIn("tf_credit_used", partner_view["arch"])

        quotation_tree = sale_model.get_view(
            view_id=self.env.ref("sale.view_quotation_tree_with_onboarding").id,
            view_type="list",
        )
        self.assertIn("tf_flow_state", quotation_tree["arch"])
        self.assertIn("tf_shipment_type", quotation_tree["arch"])

        order_tree = sale_model.get_view(
            view_id=self.env.ref("sale.view_order_tree").id,
            view_type="list",
        )
        self.assertIn("tf_flow_state", order_tree["arch"])
        self.assertIn("tf_shipment_type", order_tree["arch"])

        search_view = sale_model.get_view(
            view_id=self.env.ref("sale.view_sales_order_filter").id,
            view_type="search",
        )
        self.assertIn("tf_flow_approved", search_view["arch"])
        self.assertIn("tf_flow_state", search_view["arch"])
        self.assertIn("tf_shipment_type", search_view["arch"])
        self.assertIn("For Approval", search_view["arch"])

        form_arch = etree.fromstring(form_view["arch"].encode())
        self.assertFalse(form_arch.xpath("//label[@for='pricelist_id']"))
        self.assertFalse(form_arch.xpath("//button[@name='action_update_prices']"))
        payment_term_field = form_arch.xpath("//field[@name='payment_term_id']")[0]
        pricelist_field = form_arch.xpath("//field[@name='pricelist_id']")[0]
        customer_ref_main = form_arch.xpath("//group[@name='partner_details']//field[@name='client_order_ref']")
        customer_ref_other = form_arch.xpath("//page[@name='other_information']//field[@name='client_order_ref']")
        self.assertEqual(pricelist_field.get("invisible"), "1")
        self.assertEqual(payment_term_field.get("invisible"), "1")
        self.assertTrue(customer_ref_main)
        self.assertEqual(customer_ref_other[0].get("invisible"), "1")
        self.assertTrue(form_arch.xpath("//group[@name='partner_details']//field[@name='tag_ids']"))

        template_view = self.env["sale.order.template"].get_view(
            view_id=self.env.ref("sale_management.sale_order_template_view_form").id,
            view_type="form",
        )
        self.assertIn("tf_shipment_type", template_view["arch"])

        picking_model = self.env["stock.picking"]
        self.assertIn("tf_customer_reference", picking_model._fields)
        self.assertIn("tf_address_note", picking_model._fields)
        picking_view = picking_model.get_view(
            view_id=self.env.ref("stock.view_picking_form").id,
            view_type="form",
        )
        self.assertIn("tf_customer_reference", picking_view["arch"])
        self.assertIn("tf_address_note", picking_view["arch"])
        self.assertIn('open_attachments="True"', picking_view["arch"])

    def test_dispatch_container_field_uses_container_number_label(self):
        dispatch_model = self.env["tf.dispatch.ticket"]
        self.assertEqual(dispatch_model._fields["container_plan_id"].string, "Container")
        self.assertEqual(dispatch_model._fields["container_number"].string, "Container Number")

        partner = self._create_partner("Dispatch Container Number Partner")
        container_product = self._create_product("Dispatch Container Number Product", is_container=True)
        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "client_order_ref": "CUST-REF-001",
            "tf_address_note": "Dock door 4",
            "tf_special_instructions": "Call before arrival",
        })
        container_line = self._create_so_line(sale_order, container_product, 1.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        container_plan = container_line.tf_serial_plan_ids[:1]
        container_plan.tf_container_number = "REAL-CONT-001"

        dispatch = self.env["tf.dispatch.ticket"].create({
            "sale_order_id": sale_order.id,
            "container_plan_id": container_plan.id,
        })
        self.assertEqual(dispatch.container_number, "REAL-CONT-001")
        self.assertEqual(dispatch.customer_reference, "CUST-REF-001")
        self.assertEqual(dispatch.tf_address_note, "Dock door 4")
        self.assertIn("Container: REAL-CONT-001", dispatch.whatsapp_message_preview)
        self.assertIn("Customer Reference: CUST-REF-001", dispatch.whatsapp_message_preview)
        self.assertIn("Customer: Dispatch Container Number Partner", dispatch.whatsapp_message_preview)
        self.assertIn("Contact: Dispatch Container Number Partner", dispatch.whatsapp_message_preview)
        self.assertEqual(
            container_plan.with_context(tf_display_container_number=True).display_name,
            "REAL-CONT-001",
        )

        form_view = dispatch_model.get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_dispatch_ticket_form").id,
            view_type="form",
        )
        list_view = dispatch_model.get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_dispatch_ticket_list").id,
            view_type="list",
        )
        self.assertIn("container_number", form_view["arch"])
        self.assertIn("customer_reference", form_view["arch"])
        self.assertIn("tf_address_note", form_view["arch"])
        self.assertIn('open_attachments="True"', form_view["arch"])
        self.assertIn("container_number", list_view["arch"])
        form_arch = etree.fromstring(form_view["arch"].encode())
        container_field = form_arch.xpath("//field[@name='container_plan_id']")[0]
        self.assertEqual(container_field.get("string"), "Container Number")
        self.assertIn("tf_display_container_number", container_field.get("context"))

    def test_sale_order_context_pushes_to_connected_inventory_docs(self):
        partner = self._create_partner("Instruction Push Partner")
        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "client_order_ref": "REF-PUSH-001",
            "tf_address_note": "Use north gate",
            "tf_special_instructions": "Fragile freight",
        })
        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(incoming_type)

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": partner.id,
            "origin": sale_order.name,
            "tf_sale_order_id": sale_order.id,
        })

        self.assertEqual(picking.tf_customer_reference, "REF-PUSH-001")
        self.assertEqual(picking.tf_address_note, "Use north gate")

    def test_assignment_wizard_quantity_is_editable(self):
        wizard_model = self.env["tf.sale.serial.wizard"]
        self.assertFalse(wizard_model._fields["qty"].readonly)

        form_view = wizard_model.get_view(
            view_id=self.env.ref("tf_serial_quote_attributes.view_tf_sale_serial_wizard_form").id,
            view_type="form",
        )
        form_arch = etree.fromstring(form_view["arch"].encode())
        qty_field = form_arch.xpath("//field[@name='qty']")[0]
        self.assertEqual(qty_field.get("readonly"), "0")

    def test_serial_wizard_converts_cm_to_inches(self):
        partner = self._create_partner("Dimension Conversion Partner")
        product = self._create_product("Dimension Conversion Case")
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        line = self._create_so_line(sale_order, product, 2.0)

        wizard = self._open_wizard(line)
        ordered_lines = wizard.line_ids.sorted(lambda item: (item.sequence, item.id))
        ordered_lines[0].write({
            "tf_length": 10.0,
            "tf_width": 5.0,
            "tf_height": 2.54,
            "tf_dimension_unit": "cm",
        })
        ordered_lines[1].write({
            "tf_length": 1.0,
            "tf_width": 1.0,
            "tf_height": 1.0,
            "tf_dimension_unit": "in",
        })

        wizard.action_tf_convert_cm_to_inches()

        converted_line, untouched_line = wizard.line_ids.sorted(lambda item: (item.sequence, item.id))
        self.assertEqual(converted_line.tf_dimension_unit, "in")
        self.assertEqual(converted_line.tf_length, 3.94)
        self.assertEqual(converted_line.tf_width, 1.97)
        self.assertEqual(converted_line.tf_height, 1.0)
        self.assertEqual(untouched_line.tf_length, 1.0)
        self.assertEqual(untouched_line.tf_dimension_unit, "in")

    def test_customer_credit_limit_tracks_manual_and_60_day_clear(self):
        partner = self._create_partner("Credit Control Partner")
        partner.tf_credit_limit = 0.5
        product = self.env["product.template"].create({
            "name": "Credit Control Service",
            "type": "service",
            "sale_ok": True,
            "purchase_ok": False,
            "invoice_policy": "order",
            "list_price": 150.0,
        }).product_variant_id

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        self._create_so_line(sale_order, product, 1.0)
        sale_order.action_confirm()

        partner.invalidate_recordset(["tf_credit_used", "tf_credit_available", "tf_credit_over_limit"])
        self.assertEqual(partner.tf_credit_used, sale_order.amount_total)
        self.assertTrue(partner.tf_credit_over_limit)

        partner.action_tf_clear_credit_now()
        sale_order.invalidate_recordset(["tf_credit_state"])
        partner.invalidate_recordset(["tf_credit_used", "tf_credit_available", "tf_credit_over_limit"])
        self.assertEqual(sale_order.tf_credit_state, "cleared")
        self.assertEqual(partner.tf_credit_used, 0.0)

        sale_order.write({
            "tf_credit_state": "pending_clear",
            "tf_credit_clear_date": fields.Date.context_today(self) - timedelta(days=1),
            "tf_credit_cleared_on": False,
            "tf_credit_cleared_by_id": False,
        })
        self.env["sale.order"]._cron_tf_process_customer_credit_limits()
        sale_order.invalidate_recordset(["tf_credit_state", "tf_credit_clear_date"])
        self.assertEqual(sale_order.tf_credit_state, "cleared")
        self.assertFalse(sale_order.tf_credit_clear_date)

    def test_new_product_defaults_to_service_and_logistics_flags_force_stock_defaults(self):
        self.assertEqual(
            self.env["product.template"].default_get(["name", "type"]).get("type"),
            "service",
        )
        self.assertEqual(
            self.env["product.product"].default_get(["name", "type"]).get("type"),
            "service",
        )

        service_product = self.env["product.template"].create({
            "name": "Default Service Product",
        })
        self.assertEqual(service_product.type, "service")

        container_product = self.env["product.template"].create({
            "name": "Auto Logistics Container",
            "tf_is_container": True,
        })
        self.assertEqual(container_product.type, "consu")
        self.assertEqual(container_product.tracking, "serial")
        self.assertTrue(container_product.is_storable)

        direct_flow_product = self.env["product.template"].create({
            "name": "Intact Delivery Flow Product",
            "tf_direct_container_to_client": True,
        })
        self.assertEqual(direct_flow_product.type, "service")
        self.assertFalse(direct_flow_product.tf_is_container)
        self.assertFalse(direct_flow_product.tf_requires_container)

    def test_quotation_template_sets_sales_order_flow_type(self):
        partner = self._create_partner("Template Flow Partner")
        template = self.env["sale.order.template"].create({
            "name": "Export Template",
            "tf_shipment_type": "export",
        })

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "sale_order_template_id": template.id,
        })
        self.assertEqual(sale_order.tf_shipment_type, "export")

        onchange_order = self.env["sale.order"].new({
            "partner_id": partner.id,
            "sale_order_template_id": template.id,
        })
        onchange_order._onchange_sale_order_template_id()
        self.assertEqual(onchange_order.tf_shipment_type, "export")

    def test_sales_order_confirm_moves_flow_to_for_approval(self):
        partner = self._create_partner("Confirm Flow Partner")
        product = self.env["product.template"].create({
            "name": "Confirm Flow Service",
            "type": "service",
            "tracking": "none",
            "sale_ok": True,
            "purchase_ok": False,
            "list_price": 1.0,
        }).product_variant_id
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        self._create_so_line(sale_order, product, 1.0)

        sale_order.action_confirm()
        sale_order.invalidate_recordset(["state", "tf_flow_state"])
        self.assertEqual(sale_order.state, "sale")
        self.assertEqual(sale_order.tf_flow_state, "to_approve")

    def test_custom_logistics_lines_do_not_create_standard_delivery_on_confirm(self):
        partner = self._create_partner("Confirm Logistics Partner")
        container_product = self._create_product("Confirm Container", is_container=True)
        case_product = self._create_product("Confirm Case", requires_container=True)
        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "tf_shipment_type": "import",
        })
        self._create_so_line(sale_order, container_product, 1.0)
        self._create_so_line(sale_order, case_product, 2.0)

        sale_order.action_confirm()
        sale_order.invalidate_recordset(["state", "tf_flow_state", "delivery_count", "picking_ids"])
        self.assertEqual(sale_order.state, "sale")
        self.assertEqual(sale_order.tf_flow_state, "to_approve")
        self.assertEqual(sale_order.delivery_count, 0)
        self.assertFalse(sale_order.picking_ids)

    def test_inventory_wh_stock_action_uses_stock_lot_view(self):
        action = self.env.ref("tf_container_tracking.action_tf_container_wh_stock")
        self.assertEqual(action.res_model, "stock.lot")
        self.assertEqual(action.search_view_id, self.env.ref("stock.search_product_lot_filter"))
        self.assertIn("allowed_company_ids", action.domain)
        self.assertIn("search_default_on_hand", action.context)

    def test_sales_order_views_gate_container_and_delivery_buttons_until_approved(self):
        sale_model = self.env["sale.order"]
        form_view = sale_model.get_view(
            view_id=self.env.ref("sale.view_order_form").id,
            view_type="form",
        )
        form_arch = etree.fromstring(form_view["arch"].encode())

        container_button = form_arch.xpath("//button[@name='action_open_tf_container_tracking']")[0]
        dispatch_button = form_arch.xpath("//button[@name='action_open_tf_dispatch_tickets']")[0]
        delivery_button = form_arch.xpath("//button[@name='action_view_delivery']")[0]

        self.assertIn("tf_flow_state not in ['approved', 'completed']", container_button.get("invisible"))
        self.assertIn("tf_flow_state not in ['approved', 'completed']", dispatch_button.get("invisible"))
        self.assertIn("tf_flow_state not in ['approved', 'completed']", delivery_button.get("invisible"))

        dashboard_action = self.env.ref("tf_container_tracking.action_tf_container_tracking_dashboard")
        self.assertIn("order_id.tf_flow_state", dashboard_action.domain)
        dashboard_view = self.env["tf.sale.serial.plan"].get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_container_dashboard_form").id,
            view_type="form",
        )
        self.assertIn("action_undo_ready_dispatch_receiving", dashboard_view["arch"])
        self.assertIn('open_attachments="True"', dashboard_view["arch"])
        undo_action = self.env.ref("tf_container_tracking.action_tf_container_undo_ready")
        self.assertEqual(undo_action.binding_view_types, "form,list")

    def test_container_assignment_flow(self):
        with self.assertRaises(ValidationError):
            self.env["product.template"].create({
                "name": "Invalid Container",
                "type": "consu",
                "tracking": "none",
                "tf_is_container": True,
            })

        partner = self._create_partner("Container QA Partner")
        container_product = self._create_product("Container Product", is_container=True)
        piece_product = self._create_product("Piece Product", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 2.0)
        piece_line = self._create_so_line(sale_order, piece_product, 4.0)

        container_wizard = self._open_wizard(container_line)
        serials = container_wizard.line_ids.sorted(lambda l: (l.sequence, l.id)).mapped("serial_name")
        prefix = (sale_order.name or "SO").replace("/", "-").replace(" ", "") + "-C"
        self.assertEqual(len(serials), 2)
        self.assertTrue(all(value.startswith(prefix) for value in serials))

        for index, line in enumerate(container_wizard.line_ids.sorted(lambda l: (l.sequence, l.id)), start=1):
            line.write({
                "tf_container_number": f"QA-CONT-{index}",
                "tf_internal_status": "planning",
                "tf_container_status": "on_water",
                "tf_ssl": "CMA-CGM",
                "tf_container_type": "HC 40FT",
            })
        container_wizard.action_apply()

        container_plans = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(len(container_plans), 2)
        self.assertTrue(all(container_plans.mapped("tf_is_container_product")))

        piece_wizard = self._open_wizard(piece_line)
        with self.assertRaises(UserError):
            piece_wizard.action_apply()

        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        piece_plans = piece_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(len(piece_plans), 4)
        self.assertTrue(all(piece_plans.mapped("tf_container_plan_id")))

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(incoming_type, "Incoming picking type is required for this test.")

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": partner.id,
            "origin": sale_order.name,
        })

        self.env["stock.move"].create({
            "description_picking": container_product.display_name,
            "picking_id": picking.id,
            "product_id": container_product.id,
            "product_uom": container_product.uom_id.id,
            "product_uom_qty": 2.0,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "sale_line_id": container_line.id,
        })
        self.env["stock.move"].create({
            "description_picking": piece_product.display_name,
            "picking_id": picking.id,
            "product_id": piece_product.id,
            "product_uom": piece_product.uom_id.id,
            "product_uom_qty": 4.0,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "sale_line_id": piece_line.id,
        })

        picking.action_confirm()
        picking._tf_prefill_incoming_from_sale_serial_plan()

        piece_move_lines = picking.move_line_ids.filtered(lambda ml: ml.product_id == piece_product)
        self.assertTrue(piece_move_lines)
        self.assertTrue(all(piece_move_lines.mapped("tf_container_plan_id")))
        for index, move_line in enumerate(piece_move_lines.sorted(lambda ml: ml.id), start=1):
            move_line.lot_name = move_line.lot_name or f"PIECE-LOT-{index}"
        container_move_lines = picking.move_line_ids.filtered(lambda ml: ml.product_id == container_product)
        self.assertTrue(container_move_lines)
        self.assertTrue(all(container_move_lines.mapped("tf_internal_status")))
        self.assertTrue(all(container_move_lines.mapped("tf_container_status")))

        self._validate_picking(picking)
        self.assertEqual(picking.state, "done")

        container_plans.invalidate_recordset(["lot_id"])
        piece_plans.invalidate_recordset(["lot_id"])
        self.assertTrue(all(container_plans.mapped("lot_id")))
        self.assertTrue(all(piece_plans.mapped("lot_id")))
        self.assertTrue(all(container_plans.mapped("tf_internal_status")))
        self.assertTrue(all(container_plans.mapped("tf_container_status")))

        piece_lots = piece_plans.mapped("lot_id")
        self.assertTrue(all(piece_lots.mapped("tf_container_lot_id")))

        dashboard_rows = self.env["tf.sale.serial.plan"].search([
            ("tf_is_container_product", "=", True),
            ("order_id", "=", sale_order.id),
        ])
        self.assertEqual(len(dashboard_rows), 2)

    def test_serial_flow_regression_without_container(self):
        partner = self._create_partner("Serial Regression Partner")
        normal_piece = self._create_product("Normal Serial Piece")

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        piece_line = self._create_so_line(sale_order, normal_piece, 3.0)

        wizard = self._open_wizard(piece_line)
        self.assertEqual(len(wizard.line_ids), 3)
        wizard.action_apply()

        plans = piece_line.tf_serial_plan_ids
        self.assertEqual(len(plans), 3)
        self.assertFalse(any(plans.mapped("tf_container_plan_id")))

    def test_container_required_piece_lines_start_with_blank_serials(self):
        partner = self._create_partner("Blank Case Serial Partner")
        container_product = self._create_product("Blank Serial Container", is_container=True)
        piece_product = self._create_product("Blank Serial Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()

        piece_wizard = self._open_wizard(piece_line)
        lines = piece_wizard.line_ids.sorted(lambda l: (l.sequence, l.id))
        self.assertEqual(len(lines), 2)
        self.assertFalse(any(lines.mapped("serial_name")))

    def test_reopen_container_wizard_updates_existing_plans_without_duplicates(self):
        partner = self._create_partner("Reopen Container Partner")
        container_product = self._create_product("Reopen Container", is_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 2.0)

        first_wizard = self._open_wizard(container_line)
        first_lines = first_wizard.line_ids.sorted(lambda l: (l.sequence, l.id))
        first_lines[0].write({
            "tf_container_number": "REOPEN-C01",
            "tf_port_to_destuff": "Montreal",
        })
        first_lines[1].write({
            "tf_container_number": "REOPEN-C02",
            "tf_port_to_destuff": "Toronto",
        })
        first_wizard.action_apply()

        plans = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(len(plans), 2)

        second_wizard = self._open_wizard(container_line)
        second_lines = second_wizard.line_ids.sorted(lambda l: (l.sequence, l.id))
        second_lines[0].tf_ssl = "MSC"
        second_lines[1].tf_container_location = "Yard B"
        second_wizard.action_apply()

        updated_plans = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(len(updated_plans), 2)
        self.assertEqual(updated_plans.mapped("tf_container_number"), ["REOPEN-C01", "REOPEN-C02"])
        self.assertEqual(updated_plans[0].tf_ssl, "MSC")
        self.assertEqual(updated_plans[1].tf_container_location, "Yard B")

    def test_case_assignment_generates_requested_serial_format(self):
        partner = self._create_partner("Case Serial Format Partner")
        container_product = self._create_product("Case Format Container", is_container=True)
        piece_product = self._create_product("Case Format Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 2.0)
        piece_line = self._create_so_line(sale_order, piece_product, 5.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()
        container_plans = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(len(container_plans), 2)

        piece_wizard = self._open_wizard(piece_line)
        self.assertEqual(len(piece_wizard.assign_line_ids), 2)
        piece_wizard.assign_line_ids.sorted(lambda l: l.container_plan_id.sequence)[0].case_qty = 3
        piece_wizard.assign_line_ids.sorted(lambda l: l.container_plan_id.sequence)[1].case_qty = 2
        piece_wizard.tf_assign_length = 12.0
        piece_wizard.tf_assign_width = 12.0
        piece_wizard.tf_assign_height = 12.0
        piece_wizard.action_assign()
        piece_wizard.action_apply()

        piece_plans = piece_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(
            piece_plans.mapped("serial_name"),
            [
                f"{sale_order.name}-1 1 of 3",
                f"{sale_order.name}-1 2 of 3",
                f"{sale_order.name}-1 3 of 3",
                f"{sale_order.name}-2 1 of 2",
                f"{sale_order.name}-2 2 of 2",
            ],
        )
        self.assertEqual([plan.tf_container_plan_id.id for plan in piece_plans[:3]], [container_plans[0].id] * 3)
        self.assertEqual([plan.tf_container_plan_id.id for plan in piece_plans[3:]], [container_plans[1].id] * 2)

    def test_assign_action_recovers_container_distribution_when_transient_rows_are_lost(self):
        partner = self._create_partner("Assign Recovery Partner")
        container_product = self._create_product("Assign Recovery Container", is_container=True)
        piece_product = self._create_product("Assign Recovery Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 2.0)
        piece_line = self._create_so_line(sale_order, piece_product, 5.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()

        piece_wizard = self._open_wizard(piece_line)
        self.assertEqual(len(piece_wizard.assign_line_ids), 2)
        piece_wizard.assign_line_ids.unlink()
        self.assertFalse(piece_wizard.assign_line_ids)

        synced_lines = piece_wizard._tf_sync_assign_lines_from_order()
        self.assertEqual(len(synced_lines), 2)
        self.assertEqual(synced_lines.mapped("container_plan_id.serial_name"), [f"{sale_order.name}-C01", f"{sale_order.name}-C02"])

    def test_truck_out_opens_assignment_wizard_when_container_has_no_piece_lines(self):
        partner = self._create_partner("Truck Out Wizard Partner")
        container_product = self._create_product("Truck Out Wizard Container", is_container=True)
        piece_product = self._create_product("Truck Out Wizard Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 2.0)
        piece_line = self._create_so_line(sale_order, piece_product, 4.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()
        sale_order.action_confirm()
        sale_order.action_tf_approve()

        container_plan = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))[0]
        action = container_plan.action_truck_out_from_inventory()

        self.assertEqual(action["res_model"], "tf.sale.serial.wizard")
        wizard = self.env["tf.sale.serial.wizard"].browse(action["res_id"])
        self.assertEqual(wizard.order_line_id, piece_line)
        self.assertTrue(wizard.tf_show_assign_workflow)
        self.assertEqual(len(wizard.assign_line_ids), 2)

    def test_assign_action_preserves_case_qty_when_transient_rows_lose_container_link(self):
        partner = self._create_partner("Assign Row Link Partner")
        container_product = self._create_product("Assign Row Link Container", is_container=True)
        piece_product = self._create_product("Assign Row Link Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 3.0)
        piece_line = self._create_so_line(sale_order, piece_product, 10.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()

        piece_wizard = self._open_wizard(piece_line)
        self.assertEqual(len(piece_wizard.assign_line_ids), 3)

        piece_wizard.write({
            "assign_line_ids": [
                (5, 0, 0),
                (0, 0, {"sequence": 10, "case_qty": 5}),
                (0, 0, {"sequence": 20, "case_qty": 2}),
                (0, 0, {"sequence": 30, "case_qty": 3}),
            ],
            "tf_assign_length": 4.0,
            "tf_assign_width": 4.0,
            "tf_assign_height": 4.0,
        })

        piece_wizard.action_assign()
        serials = piece_wizard.line_ids.sorted(lambda l: (l.sequence, l.id)).mapped("serial_name")
        self.assertEqual(
            serials,
            [
                f"{sale_order.name}-1 1 of 5",
                f"{sale_order.name}-1 2 of 5",
                f"{sale_order.name}-1 3 of 5",
                f"{sale_order.name}-1 4 of 5",
                f"{sale_order.name}-1 5 of 5",
                f"{sale_order.name}-2 1 of 2",
                f"{sale_order.name}-2 2 of 2",
                f"{sale_order.name}-3 1 of 3",
                f"{sale_order.name}-3 2 of 3",
                f"{sale_order.name}-3 3 of 3",
            ],
        )

    def test_receive_container_opens_assignment_wizard_when_piece_lines_missing(self):
        partner = self._create_partner("Receive Wizard Partner")
        container_product = self._create_product("Receive Wizard Container", is_container=True)
        piece_product = self._create_product("Receive Wizard Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 3.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()
        sale_order.action_confirm()
        sale_order.action_tf_approve()

        container_plan = container_line.tf_serial_plan_ids[:1]
        action = container_plan.action_receive_container()

        self.assertEqual(action["res_model"], "tf.sale.serial.wizard")
        wizard = self.env["tf.sale.serial.wizard"].browse(action["res_id"])
        self.assertEqual(wizard.order_line_id, piece_line)

    def test_piece_description_prefill_and_receipt_sync(self):
        partner = self._create_partner("Piece Description Partner")
        piece_product = self._create_product("Piece Description Product", requires_container=False)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        wizard = self._open_wizard(piece_line)
        for idx, line in enumerate(wizard.line_ids.sorted(lambda l: (l.sequence, l.id)), start=1):
            line.tf_description = f"Desc-{idx}"
        wizard.action_apply()

        plans = piece_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(plans.mapped("tf_description"), ["Desc-1", "Desc-2"])

        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(incoming_type)

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": partner.id,
            "origin": sale_order.name,
        })
        self.env["stock.move"].create({
            "description_picking": piece_product.display_name,
            "picking_id": picking.id,
            "product_id": piece_product.id,
            "product_uom": piece_product.uom_id.id,
            "product_uom_qty": 2.0,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "sale_line_id": piece_line.id,
        })

        picking.action_confirm()
        picking._tf_prefill_incoming_from_sale_serial_plan()
        move_lines = picking.move_line_ids.sorted(lambda ml: ml.id)
        self.assertEqual(move_lines.mapped("tf_description"), ["Desc-1", "Desc-2"])

        self._validate_picking(picking)
        plans.invalidate_recordset(["lot_id", "tf_description"])
        self.assertTrue(all(plans.mapped("lot_id")))
        self.assertEqual(plans.mapped("tf_description"), ["Desc-1", "Desc-2"])
        self.assertEqual(plans.mapped("lot_id.tf_description"), ["Desc-1", "Desc-2"])

        done_line = picking.move_line_ids.sorted(lambda ml: ml.id)[0]
        self.assertTrue(done_line.tf_allow_receipt_edit)
        done_line.write({
            "tf_description": "Edited after receipt",
            "tf_length": 12.0,
            "tf_width": 13.0,
            "tf_height": 14.0,
            "tf_dimension_unit": "cm",
            "tf_weight": 15.0,
            "tf_weight_unit": "kg",
            "tf_storage_rate": "weekly",
            "tf_location_note": "Rack A1",
        })

        edited_plan = done_line.tf_sale_serial_plan_id
        edited_lot = done_line.lot_id
        edited_plan.invalidate_recordset([
            "tf_description",
            "tf_length",
            "tf_width",
            "tf_height",
            "tf_dimension_unit",
            "tf_weight",
            "tf_weight_unit",
            "tf_storage_rate",
            "tf_location_note",
        ])
        edited_lot.invalidate_recordset([
            "tf_description",
            "tf_length",
            "tf_width",
            "tf_height",
            "tf_dimension_unit",
            "tf_weight",
            "tf_weight_unit",
            "tf_storage_rate",
            "tf_location_note",
        ])
        self.assertEqual(edited_plan.tf_description, "Edited after receipt")
        self.assertEqual(edited_lot.tf_description, "Edited after receipt")
        self.assertEqual(edited_plan.tf_length, 12.0)
        self.assertEqual(edited_lot.tf_length, 12.0)
        self.assertEqual(edited_plan.tf_location_note, "Rack A1")
        self.assertEqual(edited_lot.tf_location_note, "Rack A1")

    def test_internal_status_permissions_workflow_and_history(self):
        partner = self._create_partner("Status Workflow Partner")
        container_product = self._create_product("Status Container Product", is_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(plan)
        self.assertEqual(plan.tf_internal_status, "for_approval")

        with self.assertRaises(ValidationError):
            plan.action_set_dispatch()

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        plan.invalidate_recordset(["tf_internal_status"])

        plan.action_approve_internal_status()
        self.assertEqual(plan.tf_internal_status, "tracking")
        self.assertTrue(plan._fields["tf_internal_status"].tracking)
        self.assertIn("message_ids", plan._fields)

        plan.write({"tf_container_status": "ready"})
        plan.invalidate_recordset(["tf_internal_status"])
        self.assertEqual(plan.tf_internal_status, "planning")
        plan.action_set_tracking()
        self.assertEqual(plan.tf_internal_status, "tracking")
        plan.action_set_dispatch()
        self.assertEqual(plan.tf_internal_status, "dispatch")

        group_user = self.env.ref("base.group_user")
        group_stock_user = self.env.ref("stock.group_stock_user")
        non_manager = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Non Manager User",
            "login": "non_manager_user",
            "email": "non_manager_user@example.com",
            "group_ids": [(6, 0, [group_user.id, group_stock_user.id])],
        })
        with self.assertRaises(AccessError):
            plan.with_user(non_manager).write({"tf_internal_status": "tracking"})

    def test_dispatch_ticket_completion_updates_trailer_location(self):
        partner = self._create_partner("Dispatch Partner")
        container_product = self._create_product("Dispatch Container", is_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(plan)

        trailer = self.env["tf.dispatch.trailer"].create({
            "name": "TR-01",
            "current_location": "Yard A",
        })
        ticket = self.env["tf.dispatch.ticket"].create({
            "sale_order_id": sale_order.id,
            "container_plan_id": plan.id,
            "trailer_id": trailer.id,
            "trailer_current_location": "Client Dock",
        })
        ticket.action_send_whatsapp()
        ticket.action_mark_in_progress()
        ticket.action_complete()

        self.assertEqual(ticket.state, "completed")
        self.assertTrue(ticket.completed_on)
        self.assertEqual(trailer.current_location, "Client Dock")

    def test_internal_transfer_lot_filter_by_sales_order(self):
        partner = self._create_partner("SO Filter Partner")
        product = self._create_product("SO Filter Product")
        sale_order_1 = self.env["sale.order"].create({"partner_id": partner.id})
        sale_order_2 = self.env["sale.order"].create({"partner_id": partner.id})

        lot_1 = self.env["stock.lot"].create({
            "name": "SO1-SN-01",
            "product_id": product.id,
            "tf_origin_sale_order_id": sale_order_1.id,
        })
        lot_2 = self.env["stock.lot"].create({
            "name": "SO2-SN-01",
            "product_id": product.id,
            "tf_origin_sale_order_id": sale_order_2.id,
        })

        internal_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order_1.company_id.id),
        ], limit=1)
        self.assertTrue(internal_type)
        source = internal_type.default_location_src_id
        dest = internal_type.default_location_dest_id
        self.assertTrue(source and dest)

        quant_model = self.env["stock.quant"]
        quant_model._update_available_quantity(product, source, 1.0, lot_id=lot_1)
        quant_model._update_available_quantity(product, source, 1.0, lot_id=lot_2)

        picking = self.env["stock.picking"].create({
            "picking_type_id": internal_type.id,
            "location_id": source.id,
            "location_dest_id": dest.id,
            "partner_id": partner.id,
            "tf_sale_order_id": sale_order_1.id,
            "origin": sale_order_1.name,
        })
        move = self.env["stock.move"].create({
            "description_picking": product.display_name,
            "picking_id": picking.id,
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": 1.0,
            "location_id": source.id,
            "location_dest_id": dest.id,
        })
        picking.action_confirm()
        picking.action_assign()
        line = move.move_line_ids[:1]
        self.assertTrue(line)
        line._compute_tf_allowed_lot_ids()

        self.assertIn(lot_1.id, line.tf_allowed_lot_ids.ids)
        self.assertNotIn(lot_2.id, line.tf_allowed_lot_ids.ids)

    def test_inventory_lot_truck_out_action_creates_transfer_and_dispatch_for_piece_serials(self):
        partner = self._create_partner("Stock Lot Truck Out Partner")
        container_product = self._create_product("Stock Lot Container", is_container=True)
        piece_product = self._create_product("Stock Lot Piece", requires_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 3.0)

        container_wizard = self._open_wizard(container_line)
        container_wizard.action_apply()
        container_plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(container_plan)

        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        self._receive_sale_lines(sale_order, container_line | piece_line)

        selected_lots = piece_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id)).mapped("lot_id")[:2]
        self.assertEqual(len(selected_lots), 2)

        action = selected_lots.action_tf_truck_out_selected()
        self.assertEqual(action.get("res_model"), "tf.dispatch.ticket")

        dispatch = self.env["tf.dispatch.ticket"].browse(action["res_id"])
        self.assertTrue(dispatch.internal_transfer_id)
        self.assertTrue(dispatch.delivery_order_id)
        self.assertEqual(dispatch.sale_order_id, sale_order)
        self.assertEqual(dispatch.dispatch_type, "import_dispatch")
        self.assertEqual(dispatch.container_plan_id, container_plan)

        transfer = dispatch.internal_transfer_id
        self.assertEqual(transfer.picking_type_code, "internal")
        self.assertEqual(set(transfer.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))

        delivery = dispatch.delivery_order_id
        self.assertEqual(delivery.picking_type_code, "outgoing")
        self.assertEqual(set(delivery.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))

        action_again = selected_lots.action_tf_truck_out_selected()
        self.assertEqual(action_again.get("res_id"), dispatch.id)

    def test_inventory_lot_truck_out_allows_multiple_sales_orders_for_same_customer(self):
        partner = self._create_partner("Multi SO Truck Out Partner")
        product = self._create_product("Multi SO Truck Out Case")
        sale_order_1 = self.env["sale.order"].create({"partner_id": partner.id})
        sale_order_2 = self.env["sale.order"].create({"partner_id": partner.id})
        line_1 = self._create_so_line(sale_order_1, product, 1.0)
        line_2 = self._create_so_line(sale_order_2, product, 1.0)

        self._open_wizard(line_1).action_apply()
        self._open_wizard(line_2).action_apply()
        for sale_order, line in ((sale_order_1, line_1), (sale_order_2, line_2)):
            sale_order.tf_flow_state = "approved"
            self._receive_sale_lines(sale_order, line)

        selected_lots = line_1.tf_serial_plan_ids[:1].lot_id | line_2.tf_serial_plan_ids[:1].lot_id
        self.assertEqual(len(selected_lots), 2)

        action = selected_lots.action_tf_truck_out_selected()
        self.assertEqual(action.get("res_model"), "tf.dispatch.ticket")

        dispatch = self.env["tf.dispatch.ticket"].browse(action["res_id"])
        self.assertEqual(dispatch.sale_order_ids, sale_order_1 | sale_order_2)
        self.assertTrue(dispatch.internal_transfer_id)
        self.assertTrue(dispatch.delivery_order_id)
        self.assertEqual(set(dispatch.internal_transfer_id.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))
        self.assertEqual(set(dispatch.delivery_order_id.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))

    def test_receiving_generate_serial_dialog_defaults_and_generation_do_not_crash(self):
        partner = self._create_partner("Generate Dialog Partner")
        container_product = self._create_product("Generate Dialog Container", is_container=True)
        piece_product = self._create_product("Generate Dialog Piece", requires_container=True)

        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        self._open_wizard(container_line).action_apply()
        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        container_plan = container_line.tf_serial_plan_ids[:1]
        receive_action = container_plan.action_receive_container()
        receiving = self.env["stock.picking"].browse(receive_action["res_id"])
        move = receiving.move_ids[:1]
        self.assertTrue(move)

        defaults = move.tf_get_generate_serial_dialog_defaults()
        self.assertTrue(defaults["template_move_line_ids"])

        generated_vals = move.action_generate_lot_line_vals(
            {
                "default_product_id": move.product_id.id,
                "default_location_dest_id": move.location_dest_id.id,
                "default_location_id": move.location_id.id,
                "default_tracking": move.product_id.tracking,
                "default_quantity": 2.0,
                "default_tf_template_move_line_ids": defaults["template_move_line_ids"],
                "default_tf_length": 7.0,
                "default_tf_width": 8.0,
                "default_tf_height": 9.0,
                "default_tf_dimension_unit": "cm",
                "default_tf_weight": 10.0,
                "default_tf_weight_unit": "kg",
            },
            "generate",
            "RCV-TEST-001",
            2,
            False,
        )
        self.assertEqual(len(generated_vals), 2)
        self.assertEqual(generated_vals[0]["tf_length"], 7.0)
        self.assertEqual(generated_vals[0]["tf_width"], 8.0)
        self.assertEqual(generated_vals[0]["tf_height"], 9.0)
        self.assertEqual(generated_vals[0]["tf_dimension_unit"], "cm")
        self.assertEqual(generated_vals[0]["tf_weight"], 10.0)
        self.assertEqual(generated_vals[0]["tf_weight_unit"], "kg")
        self.assertTrue(generated_vals[0]["tf_container_plan_id"])

    def test_inventory_lot_truck_out_action_creates_transfer_and_dispatch_for_container_serial(self):
        partner = self._create_partner("Stock Lot Container Truck Out Partner")
        container_product = self._create_product("Truck Out Container Product", is_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        sale_order.action_confirm()
        sale_order.action_tf_approve()
        self._receive_sale_lines(sale_order, container_line)

        container_plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(container_plan.lot_id)

        action = container_plan.lot_id.action_tf_truck_out_selected()
        self.assertEqual(action.get("res_model"), "tf.dispatch.ticket")

        dispatch = self.env["tf.dispatch.ticket"].browse(action["res_id"])
        self.assertEqual(dispatch.sale_order_id, sale_order)
        self.assertEqual(dispatch.container_plan_id, container_plan)
        self.assertTrue(dispatch.internal_transfer_id)
        self.assertEqual(dispatch.internal_transfer_id.picking_type_code, "internal")
        self.assertEqual(dispatch.internal_transfer_id.move_line_ids.mapped("lot_id").ids, container_plan.lot_id.ids)

    def test_manual_workflow_buttons_reopen_existing_records(self):
        partner = self._create_partner("Manual Workflow Partner")
        container_product = self._create_product("Manual Workflow Container", is_container=True)
        piece_product = self._create_product("Manual Workflow Piece", requires_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(plan)

        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()

        action_first_pickup = plan.action_create_pickup_dispatch_ticket()
        action_second_pickup = plan.action_create_pickup_dispatch_ticket()
        self.assertEqual(action_first_pickup.get("res_model"), "tf.dispatch.ticket")
        self.assertEqual(action_first_pickup.get("res_id"), action_second_pickup.get("res_id"))

        action_first_internal = plan.action_create_internal_transfer()
        action_second_internal = plan.action_create_internal_transfer()
        self.assertEqual(action_first_internal.get("res_model"), "stock.picking")
        self.assertEqual(action_first_internal.get("res_id"), action_second_internal.get("res_id"))

        action_first_delivery = plan.action_create_delivery_order()
        action_second_delivery = plan.action_create_delivery_order()
        self.assertEqual(action_first_delivery.get("res_model"), "stock.picking")
        self.assertEqual(action_first_delivery.get("res_id"), action_second_delivery.get("res_id"))

    def test_undo_ready_cancels_unfinished_dispatch_and_receiving(self):
        partner = self._create_partner("Undo Ready Partner")
        container_product = self._create_product("Undo Ready Container", is_container=True)
        piece_product = self._create_product("Undo Ready Piece", requires_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        self._open_wizard(container_line).action_apply()
        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        plan = container_line.tf_serial_plan_ids[:1]
        plan.write({
            "tf_port_to_destuff": "Undo Port",
            "tf_container_location": "Undo Yard",
        })

        plan.action_deliver_to_client()
        linked_pickings = self.env["stock.picking"].search([
            ("tf_container_plan_id", "=", plan.id),
            ("state", "!=", "cancel"),
        ])
        dispatch_tickets = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "in", ("delivery_leg_1", "delivery_leg_2")),
            ("state", "!=", "cancel"),
        ])
        self.assertTrue(linked_pickings)
        self.assertTrue(dispatch_tickets)

        plan.action_undo_ready_dispatch_receiving()
        plan.invalidate_recordset(["tf_container_status", "tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])
        linked_pickings.invalidate_recordset(["state"])
        dispatch_tickets.invalidate_recordset(["state"])

        self.assertEqual(plan.tf_container_status, "at_port")
        self.assertEqual(plan.tf_internal_status, "tracking")
        self.assertEqual(plan.tf_dispatch_progress, "not_dispatched")
        self.assertFalse(plan.tf_ready_on)
        self.assertFalse(linked_pickings.filtered(lambda picking: picking.exists() and picking.state != "cancel"))
        self.assertTrue(dispatch_tickets)
        self.assertTrue(all(state == "cancel" for state in dispatch_tickets.mapped("state")))

    def test_undo_ready_blocks_completed_receiving(self):
        partner = self._create_partner("Undo Ready Done Partner")
        container_product = self._create_product("Undo Ready Done Container", is_container=True)
        piece_product = self._create_product("Undo Ready Done Piece", requires_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 1.0)

        self._open_wizard(container_line).action_apply()
        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        plan = container_line.tf_serial_plan_ids[:1]
        receive_action = plan.action_receive_container()
        receiving = self.env["stock.picking"].browse(receive_action["res_id"])
        for move_line in receiving.move_line_ids:
            move_line.lot_name = f"UNDO-DONE-{move_line.id}"
            move_line.quantity = 1.0
        self._validate_picking(receiving)

        with self.assertRaises(UserError):
            plan.action_undo_ready_dispatch_receiving()

    def test_container_deliver_and_receive_leg_flow(self):
        partner = self._create_partner("Leg Flow Partner")
        container_product = self._create_product("Leg Flow Container", is_container=True)
        piece_product = self._create_product("Leg Flow Piece", requires_container=True)
        sale_order = self.env["sale.order"].create({"partner_id": partner.id})
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        piece_line = self._create_so_line(sale_order, piece_product, 2.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        plan = container_line.tf_serial_plan_ids[:1]
        plan.write({
            "tf_port_to_destuff": "Montreal Port",
            "tf_container_location": "Yard C1",
        })

        piece_wizard = self._open_wizard(piece_line)
        piece_wizard.action_auto_assign_containers()
        piece_wizard.action_apply()

        sale_order.action_confirm()
        sale_order.action_tf_approve()

        deliver_action = plan.action_deliver_to_client()
        plan.invalidate_recordset(["tf_container_status", "tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])
        self.assertEqual(plan.tf_container_status, "ready")
        self.assertEqual(plan.tf_internal_status, "planning")
        self.assertEqual(plan.tf_dispatch_progress, "delivery")
        self.assertTrue(plan.tf_ready_on)
        self.assertEqual(deliver_action["res_model"], "stock.picking")

        leg_1 = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "=", "delivery_leg_1"),
        ], limit=1)
        self.assertEqual(leg_1.dispatch_type, "delivery_leg_1")
        self.assertEqual(leg_1.location_note, "Montreal Port")
        self.assertTrue(leg_1.receiving_picking_id)
        self.assertTrue(leg_1.internal_transfer_id)
        self.assertEqual(leg_1.internal_transfer_id._tf_moves().mapped("product_id"), piece_product)
        self.assertFalse(leg_1.delivery_order_id)

        second_deliver_action = plan.action_deliver_to_client()
        self.assertEqual(second_deliver_action["res_id"], leg_1.internal_transfer_id.id)
        leg_1_again = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "=", "delivery_leg_1"),
        ])
        self.assertEqual(len(leg_1_again), 1)

        trailer = self.env["tf.dispatch.trailer"].create({
            "name": "TR-LEG",
            "current_location": "Port Gate",
        })
        leg_1.write({
            "trailer_id": trailer.id,
            "trailer_current_location": "Client Yard",
            "trailer_destination_location": "Customer Dock",
        })
        complete_action = leg_1.action_complete()
        self.assertEqual(trailer.current_location, "Customer Dock")

        leg_2 = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "=", "delivery_leg_2"),
        ], limit=1)
        self.assertTrue(leg_2)
        self.assertFalse(leg_2.delivery_order_id)
        self.assertFalse(self.env["stock.picking"].search([
            ("tf_container_plan_id", "=", plan.id),
            ("picking_type_code", "=", "outgoing"),
            ("state", "!=", "cancel"),
        ]))
        self.assertEqual(complete_action.get("res_model"), "tf.dispatch.ticket")
        self.assertEqual(complete_action.get("res_id"), leg_2.id)

        receive_action = plan.action_receive_container()
        receiving = self.env["stock.picking"].browse(receive_action["res_id"])
        self.assertEqual(receiving.id, leg_1.receiving_picking_id.id)
        self.assertEqual(receiving.picking_type_code, "incoming")
        self.assertEqual(receiving._tf_moves().mapped("product_id"), piece_product)
        for move_line in receiving.move_line_ids:
            move_line.lot_name = f"CASE-LOT-{move_line.id}"
            move_line.quantity = 1.0
        self._validate_picking(receiving)

        plan.invalidate_recordset(["tf_container_status", "tf_dispatch_progress"])
        self.assertEqual(plan.tf_container_status, "ready_for_return")
        self.assertEqual(plan.tf_dispatch_progress, "return")

        return_leg = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "=", "return_leg"),
        ], limit=1)
        self.assertTrue(return_leg)
        self.assertEqual(return_leg.receiving_picking_id, receiving)

        return_leg.write({
            "trailer_id": trailer.id,
            "trailer_current_location": "Port Return Yard",
        })
        return_leg.action_complete()

        plan.invalidate_recordset(["tf_container_status", "tf_dispatch_progress"])
        self.assertEqual(plan.tf_container_status, "returned")
        self.assertEqual(plan.tf_dispatch_progress, "completed")

    def test_direct_container_to_client_product_creates_direct_dispatch_and_delivery(self):
        partner = self._create_partner("Direct Client Partner")
        container_product = self._create_product("Direct Flow Container", is_container=True)
        direct_flow_product = self.env["product.template"].create({
            "name": "Intact Delivery",
            "tf_direct_container_to_client": True,
            "sale_ok": True,
            "list_price": 1.0,
        }).product_variant_id

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "tf_shipment_type": "import",
        })
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        self._create_so_line(sale_order, direct_flow_product, 1.0)

        wizard = self._open_wizard(container_line)
        wizard.action_apply()
        sale_order.action_confirm()
        sale_order.action_tf_approve()

        plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(plan)

        direct_action = plan.action_truck_out_from_inventory()
        direct_delivery = self.env["stock.picking"].browse(direct_action["res_id"])
        self.assertEqual(direct_action["res_model"], "stock.picking")
        self.assertEqual(direct_delivery.picking_type_code, "outgoing")
        self.assertEqual(direct_delivery.tf_flow_kind, "direct_container_client")
        self.assertEqual(direct_delivery.tf_container_plan_id, plan)
        self.assertEqual(direct_delivery.tf_sale_order_id, sale_order)

        direct_ticket = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", plan.id),
            ("dispatch_type", "=", "direct_container_client"),
            ("state", "!=", "cancel"),
        ])
        self.assertEqual(len(direct_ticket), 1)
        self.assertEqual(direct_ticket.delivery_order_id, direct_delivery)
        self.assertFalse(self.env["stock.picking"].search([
            ("tf_container_plan_id", "=", plan.id),
            ("picking_type_code", "in", ("incoming", "internal")),
            ("state", "!=", "cancel"),
        ]))

        second_action = plan.action_truck_out_from_inventory()
        self.assertEqual(second_action["res_id"], direct_delivery.id)

        trailer = self.env["tf.dispatch.trailer"].create({
            "name": "DIRECT-TRAILER",
            "current_location": "Port",
        })
        direct_ticket.write({
            "trailer_id": trailer.id,
            "trailer_destination_location": "Client",
        })
        direct_ticket.action_complete()
        plan.invalidate_recordset(["tf_container_status", "tf_dispatch_progress"])
        self.assertEqual(plan.tf_container_status, "picked_up")
        self.assertEqual(plan.tf_dispatch_progress, "completed")

    def test_sales_order_approval_creates_container_and_export_flow(self):
        partner = self._create_partner("Export Flow Partner")
        container_product = self._create_product("Export Container", is_container=True)
        case_product = self._create_product("Export Case")

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "tf_shipment_type": "export",
        })
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        case_line = self._create_so_line(sale_order, case_product, 2.0)

        sale_order.action_tf_submit_for_approval()
        self.assertEqual(sale_order.tf_flow_state, "to_approve")

        sale_order.action_tf_approve()
        self.assertEqual(sale_order.tf_flow_state, "approved")

        container_plan = container_line.tf_serial_plan_ids[:1]
        self.assertTrue(container_plan)
        self.assertEqual(container_plan.tf_internal_status, "pickup")

        sale_order.action_tf_create_export_flow()

        case_leg_1 = self.env["tf.dispatch.ticket"].search([
            ("sale_order_id", "=", sale_order.id),
            ("dispatch_type", "=", "export_case_leg_1"),
        ], limit=1)
        case_leg_2 = self.env["tf.dispatch.ticket"].search([
            ("sale_order_id", "=", sale_order.id),
            ("dispatch_type", "=", "export_case_leg_2"),
        ], limit=1)
        self.assertTrue(case_leg_1)
        self.assertTrue(case_leg_2)
        self.assertTrue(case_leg_1.receiving_picking_id)
        self.assertTrue(case_leg_2.internal_transfer_id)

        container_leg_1 = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", container_plan.id),
            ("dispatch_type", "=", "export_container_leg_1"),
        ], limit=1)
        container_leg_2 = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", container_plan.id),
            ("dispatch_type", "=", "export_container_leg_2"),
        ], limit=1)
        self.assertTrue(container_leg_1)
        self.assertTrue(container_leg_2)

        truck_out_action = container_plan.action_truck_out_from_inventory()
        truck_out = self.env["stock.picking"].browse(truck_out_action["res_id"])
        self.assertEqual(truck_out.tf_flow_kind, "container_export_leg_3")
        for move_line in truck_out.move_line_ids.filtered(lambda ml: not ml.lot_id and ml.product_id.tracking == "serial"):
            move_line.lot_name = f"EXP-{move_line.id}"
            move_line.quantity = 1.0
        self._validate_picking(truck_out)

        sale_order.invalidate_recordset(["tf_flow_state"])
        self.assertEqual(sale_order.tf_flow_state, "completed")
