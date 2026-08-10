# -*- coding: utf-8 -*-
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSpecialInstructionsRelatable(TransactionCase):
    def setUp(self):
        super().setUp()
        self.partner = self.env["res.partner"].create({"name": "Test Instructions Partner"})
        self.product = self.env["product.product"].create({
            "name": "Test Container Product",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "tf_is_container": True,
        })
        self.sale_order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "tf_special_instructions": "Initial Special Instruction Note",
        })
        self.tag = self.env["crm.tag"].create({
            "name": "Urgent Dispatch",
            "color": 2,
        })
        self.sale_order.tag_ids = [(6, 0, [self.tag.id])]
        self.sale_line = self.env["sale.order.line"].create({
            "order_id": self.sale_order.id,
            "product_id": self.product.id,
            "product_uom_qty": 1.0,
            "price_unit": 10.0,
            "name": self.product.name,
        })

    def test_fields_exist_and_relate_from_sale_order(self):
        # 1. Check sale.order field
        self.assertEqual(self.sale_order.tf_special_instructions, "Initial Special Instruction Note")

        # 2. Check tf.sale.serial.plan
        plan = self.env["tf.sale.serial.plan"].create({
            "order_id": self.sale_order.id,
            "order_line_id": self.sale_line.id,
            "serial_name": "SO-C01",
            "tf_is_container_product": True,
        })
        self.assertEqual(plan.tf_special_instructions, "Initial Special Instruction Note")
        self.assertEqual(plan.tf_sale_tag_ids, self.tag)

        # 3. Check tf.dispatch.ticket
        ticket = self.env["tf.dispatch.ticket"].create({
            "sale_order_id": self.sale_order.id,
            "container_plan_id": plan.id,
        })
        self.assertEqual(ticket.tf_special_instructions, "Initial Special Instruction Note")
        self.assertEqual(ticket.tf_sale_tag_ids, self.tag)
        self.assertIn("Special Instructions: Initial Special Instruction Note", ticket.whatsapp_message_preview)
        self.assertIn("Tags: Urgent Dispatch", ticket.whatsapp_message_preview)

        # 4. Check stock.picking
        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", self.sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(incoming_type)

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": self.partner.id,
            "tf_sale_order_id": self.sale_order.id,
            "tf_container_plan_id": plan.id,
        })
        self.assertEqual(picking.tf_special_instructions, "Initial Special Instruction Note")
        self.assertEqual(picking.tf_sale_tag_ids, self.tag)

    def test_update_from_dispatch_ticket_propagates(self):
        plan = self.env["tf.sale.serial.plan"].create({
            "order_id": self.sale_order.id,
            "order_line_id": self.sale_line.id,
            "serial_name": "SO-C02",
            "tf_is_container_product": True,
        })
        ticket = self.env["tf.dispatch.ticket"].create({
            "sale_order_id": self.sale_order.id,
            "container_plan_id": plan.id,
        })

        # Update note on dispatch ticket
        ticket.write({"tf_special_instructions": "Gate 4 entrance required!"})

        self.sale_order.invalidate_recordset(["tf_special_instructions"])
        plan.invalidate_recordset(["tf_special_instructions"])

        self.assertEqual(self.sale_order.tf_special_instructions, "Gate 4 entrance required!")
        self.assertEqual(plan.tf_special_instructions, "Gate 4 entrance required!")

    def test_update_from_stock_picking_propagates(self):
        plan = self.env["tf.sale.serial.plan"].create({
            "order_id": self.sale_order.id,
            "order_line_id": self.sale_line.id,
            "serial_name": "SO-C03",
            "tf_is_container_product": True,
        })
        ticket = self.env["tf.dispatch.ticket"].create({
            "sale_order_id": self.sale_order.id,
            "container_plan_id": plan.id,
        })
        incoming_type = self.env["stock.picking.type"].search([
            ("code", "=", "incoming"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", self.sale_order.company_id.id),
        ], limit=1)

        picking = self.env["stock.picking"].create({
            "picking_type_id": incoming_type.id,
            "location_id": incoming_type.default_location_src_id.id,
            "location_dest_id": incoming_type.default_location_dest_id.id,
            "partner_id": self.partner.id,
            "tf_container_plan_id": plan.id,
        })
        self.assertEqual(picking.tf_sale_order_id, self.sale_order)

        # Update note on picking
        picking.write({"tf_special_instructions": "Unload at Warehouse B dock"})

        self.sale_order.invalidate_recordset(["tf_special_instructions"])
        plan.invalidate_recordset(["tf_special_instructions"])
        ticket.invalidate_recordset(["tf_special_instructions"])

        self.assertEqual(self.sale_order.tf_special_instructions, "Unload at Warehouse B dock")
        self.assertEqual(plan.tf_special_instructions, "Unload at Warehouse B dock")
        self.assertEqual(ticket.tf_special_instructions, "Unload at Warehouse B dock")

    def test_views_contain_special_instructions_field(self):
        dispatch_view = self.env["tf.dispatch.ticket"].get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_dispatch_ticket_form").id,
            view_type="form",
        )
        self.assertIn("tf_special_instructions", dispatch_view["arch"])
        self.assertIn("tf_sale_tag_ids", dispatch_view["arch"])

        picking_view = self.env["stock.picking"].get_view(
            view_id=self.env.ref("tf_container_tracking.view_picking_form_tf_sale_order_link").id,
            view_type="form",
        )
        self.assertIn("tf_special_instructions", picking_view["arch"])
        self.assertIn("tf_sale_tag_ids", picking_view["arch"])

        container_view = self.env["tf.sale.serial.plan"].get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_container_dashboard_form").id,
            view_type="form",
        )
        self.assertIn("tf_special_instructions", container_view["arch"])
        self.assertIn("tf_sale_tag_ids", container_view["arch"])

    def test_duplicated_sale_order_resets_flow_state_to_draft(self):
        self.sale_order.write({"tf_flow_state": "approved"})
        self.assertEqual(self.sale_order.tf_flow_state, "approved")

        duplicated_so = self.sale_order.copy()
        self.assertEqual(duplicated_so.tf_flow_state, "draft")
