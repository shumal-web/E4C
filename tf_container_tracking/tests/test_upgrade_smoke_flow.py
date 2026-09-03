# -*- coding: utf-8 -*-
from lxml import etree

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "tf_upgrade_smoke")
class TestUpgradeSmokeFlow(TransactionCase):
    """High-value deployment smoke tests for the E4C sales-to-dispatch flow.

    This test is intentionally end-to-end. It catches the issues that usually
    only appear after a module upgrade: missing columns, broken views, broken
    serial planning, receiving, truck-out dispatch, and SO lot filtering.
    """

    def setUp(self):
        super().setUp()
        self._ensure_test_warehouse()

    def _ensure_test_warehouse(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not warehouse:
            warehouse = self.env["stock.warehouse"].create({
                "name": "E4C Smoke Warehouse",
                "code": "E4CS",
                "company_id": self.env.company.id,
            })
        self.env["stock.picking.type"].with_context(active_test=False).search([
            ("warehouse_id", "=", warehouse.id),
            ("code", "in", ["incoming", "internal", "outgoing"]),
            ("company_id", "=", self.env.company.id),
        ]).write({"active": True})

    def _create_partner(self, name, **extra):
        vals = {"name": name}
        vals.update(extra)
        return self.env["res.partner"].create(vals)

    def _create_product(self, name, is_container=False, requires_container=False, direct_flow=False, cfs_flow=False):
        template = self.env["product.template"].create({
            "name": name,
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "tf_is_container": is_container,
            "tf_requires_container": requires_container,
            "tf_direct_container_to_client": direct_flow,
            "tf_cfs_pieces_flow": cfs_flow,
            "tf_container_type": "40HC" if is_container else False,
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

    def _open_serial_wizard(self, order_line):
        return self.env["tf.sale.serial.wizard"].with_context(
            default_order_line_id=order_line.id,
        ).create({})

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
        self.assertTrue(incoming_type, "Incoming picking type is required.")

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
            move_line.lot_name = move_line.lot_name or f"SMOKE-RCV-{index}"
            move_line.quantity = 1.0
        self._validate_picking(picking)
        return picking

    def test_01_sales_to_dispatch_upgrade_smoke_flow(self):
        self._assert_critical_fields_exist()
        self._assert_critical_views_load()

        partner = self._create_partner(
            "Smoke Test Customer",
            email="smoke.customer@example.com",
            tf_credit_limit=5000.0,
        )
        dispatch_contact = self._create_partner("Smoke Dispatch Contact", parent_id=partner.id)
        tag = self.env["crm.tag"].create({"name": "Smoke Priority"})
        container_product = self._create_product("Smoke Container", is_container=True)
        case_product = self._create_product("Smoke Case", requires_container=True)

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "partner_shipping_id": partner.id,
            "client_order_ref": "SMOKE-CUST-REF",
            "tf_dispatch_contact_id": dispatch_contact.id,
            "tf_shipment_type": "import",
            "tf_address_note": "Smoke dock address",
            "tf_shipper_note": "Smoke shipper",
            "tf_consignee_note": "Smoke consignee",
            "tf_special_instructions": "Smoke handling note",
            "tag_ids": [(6, 0, tag.ids)],
        })
        container_line = self._create_so_line(sale_order, container_product, 2.0)
        case_line = self._create_so_line(sale_order, case_product, 3.0)

        container_wizard = self._open_serial_wizard(container_line)
        self.assertEqual(len(container_wizard.line_ids), 2)
        container_wizard.action_apply()
        container_plans = container_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(container_plans.mapped("serial_name"), [f"{sale_order.name}-C01", f"{sale_order.name}-C02"])
        self.assertEqual(container_plans.mapped("tf_container_number"), [f"{sale_order.name}-C01", f"{sale_order.name}-C02"])
        self.assertEqual(set(container_plans.mapped("tf_container_type")), {"40HC"})

        case_wizard = self._open_serial_wizard(case_line)
        self.assertEqual(len(case_wizard.assign_line_ids), 2)
        case_wizard.assign_line_ids[0].case_qty = 2
        case_wizard.assign_line_ids[1].case_qty = 1
        case_wizard.write({
            "tf_assign_length": 10.0,
            "tf_assign_width": 5.0,
            "tf_assign_height": 4.0,
            "tf_assign_dimension_unit": "cm",
            "tf_assign_weight": 100.0,
            "tf_assign_weight_unit": "kg",
        })
        case_wizard.action_assign()
        expected_case_serials = [
            f"{sale_order.name}-1 1 of 2",
            f"{sale_order.name}-1 2 of 2",
            f"{sale_order.name}-2 1 of 1",
        ]
        self.assertEqual(case_wizard.line_ids.sorted(lambda l: (l.sequence, l.id)).mapped("serial_name"), expected_case_serials)
        case_wizard.action_apply()
        case_plans = case_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        self.assertEqual(case_plans.mapped("serial_name"), expected_case_serials)
        self.assertEqual(case_plans.mapped("tf_container_plan_id"), container_plans[0] | container_plans[1])
        self.assertEqual(set(case_plans.mapped("tf_dimension_unit")), {"cm"})
        self.assertEqual(set(case_plans.mapped("tf_weight_unit")), {"kg"})

        sale_order.action_confirm()
        sale_order.action_tf_approve()
        self.assertEqual(sale_order.tf_flow_state, "approved")

        receiving = self._receive_sale_lines(sale_order, container_line | case_line)
        self.assertEqual(receiving.state, "done")
        self.assertEqual(len(case_plans.mapped("lot_id")), 3)
        self.assertEqual(case_plans.mapped("lot_id").mapped("tf_origin_sale_order_id"), sale_order)

        selected_lots = case_plans[:2].mapped("lot_id")
        action = selected_lots.action_tf_truck_out_selected()
        self.assertEqual(action.get("res_model"), "tf.dispatch.ticket")
        dispatch = self.env["tf.dispatch.ticket"].browse(action["res_id"])
        self.assertEqual(dispatch.sale_order_id, sale_order)
        self.assertEqual(dispatch.sale_order_ids, sale_order)
        self.assertEqual(dispatch.dispatch_type, "import_dispatch")
        self.assertTrue(dispatch.internal_transfer_id)
        self.assertTrue(dispatch.delivery_order_id)
        self.assertEqual(dispatch.internal_transfer_id.picking_type_code, "internal")
        self.assertEqual(dispatch.delivery_order_id.picking_type_code, "outgoing")
        self.assertEqual(set(dispatch.internal_transfer_id.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))
        self.assertEqual(set(dispatch.delivery_order_id.move_line_ids.mapped("lot_id").ids), set(selected_lots.ids))
        self.assertIn("Special Instructions: Smoke handling note", dispatch.whatsapp_message_preview)
        self.assertIn("Tags: Smoke Priority", dispatch.whatsapp_message_preview)

        dispatch.action_send_whatsapp()
        self.assertTrue(dispatch.whatsapp_sent)
        self.assertEqual(dispatch.state, "sent")
        dispatch.action_mark_in_progress()
        self.assertEqual(dispatch.state, "in_progress")
        trailer = self.env["tf.dispatch.trailer"].create({
            "name": "SMOKE-TRAILER",
            "current_location": "Warehouse",
        })
        dispatch.write({
            "trailer_id": trailer.id,
            "trailer_destination_location": "Client Yard",
        })
        dispatch.action_complete()
        self.assertEqual(dispatch.state, "completed")
        self.assertEqual(trailer.current_location, "Client Yard")

        self._assert_so_lot_filter(sale_order, case_product, selected_lots[:1])

    def test_02_direct_container_to_client_smoke_flow(self):
        partner = self._create_partner("Smoke Direct Customer")
        container_product = self._create_product("Smoke Direct Container", is_container=True)
        direct_product = self._create_product("Smoke Direct Delivery Service", direct_flow=True)

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "tf_shipment_type": "import",
        })
        container_line = self._create_so_line(sale_order, container_product, 1.0)
        self._create_so_line(sale_order, direct_product, 1.0)
        self._open_serial_wizard(container_line).action_apply()
        sale_order.action_confirm()
        sale_order.action_tf_approve()

        container_plan = container_line.tf_serial_plan_ids[:1]
        action = container_plan.action_truck_out_from_inventory()
        self.assertEqual(action.get("res_model"), "stock.picking")
        delivery = self.env["stock.picking"].browse(action["res_id"])
        self.assertEqual(delivery.picking_type_code, "outgoing")
        self.assertEqual(delivery.tf_flow_kind, "direct_container_client")
        self.assertEqual(delivery.tf_container_plan_id, container_plan)

        dispatch = self.env["tf.dispatch.ticket"].search([
            ("container_plan_id", "=", container_plan.id),
            ("dispatch_type", "=", "direct_container_client"),
            ("state", "!=", "cancel"),
        ])
        self.assertEqual(len(dispatch), 1)
        self.assertEqual(dispatch.delivery_order_id, delivery)
        self.assertFalse(self.env["stock.picking"].search([
            ("tf_container_plan_id", "=", container_plan.id),
            ("picking_type_code", "in", ("incoming", "internal")),
            ("state", "!=", "cancel"),
        ]))

    def test_03_cfs_pieces_upgrade_smoke_flow(self):
        partner = self._create_partner("Smoke CFS Customer")
        contact = self._create_partner("Smoke CFS Contact", parent_id=partner.id)
        cfs_product = self._create_product("Smoke CFS Pieces", cfs_flow=True)

        sale_order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "partner_shipping_id": partner.id,
            "tf_dispatch_contact_id": contact.id,
            "tf_shipper_note": "Smoke CFS shipper",
            "tf_consignee_note": "Smoke CFS consignee",
        })
        self._create_so_line(sale_order, cfs_product, 1.0)

        sale_order.action_confirm()
        sale_order.action_tf_approve()

        tickets = self.env["tf.dispatch.ticket"].search([
            ("sale_order_id", "=", sale_order.id),
            ("dispatch_type", "in", ("cfs_piece_pickup_leg_1", "cfs_piece_delivery_leg_2")),
            ("state", "!=", "cancel"),
        ])
        self.assertEqual(len(tickets), 2)
        self.assertEqual(set(tickets.mapped("contact_id").ids), set(contact.ids))
        self.assertFalse(sale_order.picking_ids)

    def _assert_critical_fields_exist(self):
        field_checks = {
            "sale.order": [
                "tf_flow_state",
                "tf_shipment_type",
                "tf_container_tracking_count",
                "tf_dispatch_ticket_count",
                "tf_address_note",
                "tf_shipper_note",
                "tf_consignee_note",
                "tf_special_instructions",
                "tf_credit_state",
            ],
            "sale.order.template": [
                "tf_shipment_type",
                "tf_address_note",
                "tf_shipper_note",
                "tf_consignee_note",
                "tf_special_instructions",
            ],
            "product.template": [
                "tf_container_type",
                "tf_direct_container_to_client",
                "tf_cfs_pieces_flow",
                "tf_is_container",
                "tf_requires_container",
            ],
            "tf.dispatch.ticket": [
                "whatsapp_sent",
                "whatsapp_message_preview",
                "internal_transfer_id",
                "delivery_order_id",
                "container_number",
            ],
            "tf.sale.serial.plan": ["tf_ssl", "tf_port_to_destuff"],
            "stock.lot": ["tf_origin_sale_order_id", "tf_container_lot_id", "tf_ssl", "tf_port_to_destuff"],
            "stock.move.line": ["tf_allowed_lot_ids", "tf_ssl", "tf_port_to_destuff"],
        }
        for model_name, field_names in field_checks.items():
            model = self.env[model_name]
            for field_name in field_names:
                self.assertIn(field_name, model._fields, f"Missing field {model_name}.{field_name}")
        self.assertEqual(self.env["tf.sale.serial.plan"]._fields["tf_ssl"].type, "selection")
        self.assertEqual(self.env["tf.sale.serial.plan"]._fields["tf_port_to_destuff"].type, "selection")

    def _assert_critical_views_load(self):
        view_checks = [
            ("sale.order", "sale.view_order_form", "form"),
            ("sale.order", "sale.view_quotation_tree_with_onboarding", "list"),
            ("sale.order", "sale.view_order_tree", "list"),
            ("sale.order", "sale.view_sales_order_filter", "search"),
            ("product.template", "product.product_template_form_view", "form"),
            ("stock.picking", "stock.view_picking_form", "form"),
            ("stock.lot", "stock.view_production_lot_tree", "list"),
            ("tf.dispatch.ticket", "tf_container_tracking.view_tf_dispatch_ticket_form", "form"),
            ("tf.dispatch.ticket", "tf_container_tracking.view_tf_dispatch_ticket_list", "list"),
            ("tf.sale.serial.plan", "tf_container_tracking.view_tf_container_dashboard_tree", "list"),
        ]
        for model_name, xmlid, view_type in view_checks:
            view = self.env[model_name].get_view(
                view_id=self.env.ref(xmlid).id,
                view_type=view_type,
            )
            self.assertTrue(view["arch"], f"View did not load: {xmlid}")

        for xmlid in ("sale.view_quotation_tree_with_onboarding", "sale.view_order_tree"):
            tree_view = self.env["sale.order"].get_view(
                view_id=self.env.ref(xmlid).id,
                view_type="list",
            )
            tree_arch = etree.fromstring(tree_view["arch"].encode())
            for button in tree_arch.xpath("//header/button"):
                self.assertNotIn("tf_flow_state", button.get("invisible") or "")

    def _assert_so_lot_filter(self, sale_order, product, expected_lots):
        other_order = self.env["sale.order"].create({"partner_id": sale_order.partner_id.id})
        other_lot = self.env["stock.lot"].create({
            "name": "SMOKE-OTHER-SO-LOT",
            "product_id": product.id,
            "tf_origin_sale_order_id": other_order.id,
        })
        internal_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", sale_order.company_id.id),
        ], limit=1)
        self.assertTrue(internal_type, "Internal picking type is required.")
        source = internal_type.default_location_src_id
        for lot in expected_lots:
            self.env["stock.quant"]._update_available_quantity(product, source, 1.0, lot_id=lot)
        self.env["stock.quant"]._update_available_quantity(product, source, 1.0, lot_id=other_lot)

        picking = self.env["stock.picking"].create({
            "picking_type_id": internal_type.id,
            "location_id": source.id,
            "location_dest_id": internal_type.default_location_dest_id.id,
            "partner_id": sale_order.partner_id.id,
            "tf_sale_order_id": sale_order.id,
            "origin": sale_order.name,
        })
        move = self.env["stock.move"].create({
            "description_picking": product.display_name,
            "picking_id": picking.id,
            "product_id": product.id,
            "product_uom": product.uom_id.id,
            "product_uom_qty": 1.0,
            "location_id": source.id,
            "location_dest_id": internal_type.default_location_dest_id.id,
        })
        picking.action_confirm()
        picking.action_assign()
        line = move.move_line_ids[:1]
        self.assertTrue(line, "Internal transfer move line was not created.")
        line._compute_tf_allowed_lot_ids()
        self.assertTrue(set(expected_lots.ids).intersection(line.tf_allowed_lot_ids.ids))
        self.assertNotIn(other_lot.id, line.tf_allowed_lot_ids.ids)
