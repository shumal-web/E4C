# -*- coding: utf-8 -*-
from io import BytesIO

from lxml import etree
from PyPDF2 import PdfFileReader

from odoo.tests.common import TransactionCase


class TestE4CPrintouts(TransactionCase):
    def setUp(self):
        super().setUp()
        # Odoo's TransactionCase is single-process; point wkhtmltopdf at a closed
        # port so report asset lookups fail fast instead of deadlocking the suite.
        self.env["ir.config_parameter"].sudo().set_param("report.url", "http://127.0.0.1:9")
        self._ensure_test_warehouse()
        self.partner = self.env["res.partner"].create({
            "name": "Printout Customer",
            "street": "100 Test Street",
            "city": "Montreal",
            "zip": "H1H 1H1",
        })
        self.container_product = self.env["product.product"].create({
            "name": "Printout Container",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "tf_is_container": True,
            "sale_ok": True,
        })
        self.case_product = self.env["product.product"].create({
            "name": "Printout Case",
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
            "tf_requires_container": True,
            "sale_ok": True,
        })
        self.sale_order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "client_order_ref": "PO-PRINT-001",
            "tf_address_note": "Dock 3, Montreal warehouse",
            "tf_shipper_note": "Printout Shipper",
            "tf_consignee_note": "Printout Consignee",
            "tf_special_instructions": "Call before arrival",
        })
        self.container_line = self.env["sale.order.line"].create({
            "order_id": self.sale_order.id,
            "product_id": self.container_product.id,
            "product_uom_qty": 1.0,
            "product_uom_id": self.container_product.uom_id.id,
            "price_unit": 1.0,
            "name": self.container_product.display_name,
        })
        self.case_line = self.env["sale.order.line"].create({
            "order_id": self.sale_order.id,
            "product_id": self.case_product.id,
            "product_uom_qty": 1.0,
            "product_uom_id": self.case_product.uom_id.id,
            "price_unit": 1.0,
            "name": self.case_product.display_name,
        })
        self.container_plan = self.env["tf.sale.serial.plan"].create({
            "order_id": self.sale_order.id,
            "order_line_id": self.container_line.id,
            "serial_name": "SOPRINT-C01",
            "tf_container_number": "SOPRINT-C01",
            "tf_container_type": "40HC",
            "tf_pubk_no": "BK-001",
            "tf_ssl": "MSC",
            "tf_weight": 1000,
            "tf_weight_unit": "kg",
        })
        self.container_lot = self.env["stock.lot"].create({
            "name": self.container_plan.serial_name,
            "product_id": self.container_product.id,
            "company_id": self.env.company.id,
            "tf_origin_sale_order_id": self.sale_order.id,
            "tf_description": "Container",
        })
        self.container_plan.lot_id = self.container_lot.id
        self.case_plan = self.env["tf.sale.serial.plan"].create({
            "order_id": self.sale_order.id,
            "order_line_id": self.case_line.id,
            "serial_name": "SOPRINT-1 1 of 1",
            "tf_container_plan_id": self.container_plan.id,
            "tf_description": "Fragile Case",
            "tf_length": 10.0,
            "tf_width": 5.0,
            "tf_height": 4.0,
            "tf_dimension_unit": "in",
            "tf_weight": 75.0,
            "tf_weight_unit": "lb",
            "tf_location_note": "Aisle 4",
        })
        self.case_lot = self.env["stock.lot"].create({
            "name": self.case_plan.serial_name,
            "product_id": self.case_product.id,
            "company_id": self.env.company.id,
            "tf_origin_sale_order_id": self.sale_order.id,
            "tf_container_lot_id": self.container_lot.id,
            "tf_description": "Fragile Case",
            "tf_length": 10.0,
            "tf_width": 5.0,
            "tf_height": 4.0,
            "tf_dimension_unit": "in",
            "tf_weight": 75.0,
            "tf_weight_unit": "lb",
            "tf_location_note": "Aisle 4",
        })
        self.picking = self._create_stock_picking()
        self.dispatch = self.env["tf.dispatch.ticket"].create({
            "dispatch_type": "import_dispatch",
            "sale_order_id": self.sale_order.id,
            "sale_order_ids": [(6, 0, [self.sale_order.id])],
            "container_plan_id": self.container_plan.id,
            "location_note": "WH/Stock",
            "internal_transfer_id": self.picking.id,
        })

    def _ensure_test_warehouse(self):
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)],
            limit=1,
        )
        if not warehouse:
            warehouse = self.env["stock.warehouse"].create({
                "name": "E4C Test Warehouse",
                "code": "E4CT",
                "company_id": self.env.company.id,
            })
        self.env["stock.picking.type"].with_context(active_test=False).search([
            ("warehouse_id", "=", warehouse.id),
            ("code", "in", ["incoming", "internal", "outgoing"]),
            ("company_id", "=", self.env.company.id),
        ]).write({"active": True})

    def _create_stock_picking(self):
        picking_type = self.env["stock.picking.type"].search([
            ("code", "=", "internal"),
            ("warehouse_id", "!=", False),
            ("company_id", "=", self.env.company.id),
        ], limit=1)
        self.assertTrue(picking_type, "Internal picking type is required for printout tests.")
        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "location_id": picking_type.default_location_src_id.id,
            "location_dest_id": picking_type.default_location_dest_id.id,
            "partner_id": self.partner.id,
            "origin": self.sale_order.name,
            "tf_sale_order_id": self.sale_order.id,
            "tf_container_plan_id": self.container_plan.id,
            "tf_flow_kind": "import_truck_out",
        })
        move = self.env["stock.move"].create({
            "description_picking": "Fragile Case",
            "picking_id": picking.id,
            "product_id": self.case_product.id,
            "product_uom": self.case_product.uom_id.id,
            "product_uom_qty": 1.0,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
            "sale_line_id": self.case_line.id,
        })
        picking.action_confirm()
        picking._tf_cleanup_placeholder_move_lines(picking)
        self.env["stock.move.line"].create({
            "move_id": move.id,
            "picking_id": picking.id,
            "company_id": self.env.company.id,
            "product_id": self.case_product.id,
            "product_uom_id": self.case_product.uom_id.id,
            "location_id": picking.location_id.id,
            "location_dest_id": picking.location_dest_id.id,
            "quantity": 1.0,
            "lot_id": self.case_lot.id,
            "tf_sale_serial_plan_id": self.case_plan.id,
            "tf_container_plan_id": self.container_plan.id,
            "tf_description": "Fragile Case",
            "tf_length": 10.0,
            "tf_width": 5.0,
            "tf_height": 4.0,
            "tf_dimension_unit": "in",
            "tf_weight": 75.0,
            "tf_weight_unit": "lb",
            "tf_location_note": "Aisle 4",
        })
        return picking

    def _render_html(self, report_name, record):
        html = self.env["ir.actions.report"]._render_qweb_html(report_name, record.ids)[0]
        if isinstance(html, bytes):
            html = html.decode("utf-8")
        return html

    def _render_pdf(self, report_xmlid, record):
        pdf_content, output_type = self.env["ir.actions.report"].with_context(force_report_rendering=True)._render_qweb_pdf(
            report_xmlid,
            record.ids,
        )
        return pdf_content, output_type

    def test_report_actions_exist(self):
        report_ids = [
            "tf_e4c_printouts.action_report_e4c_receiving_labels",
            "tf_e4c_printouts.action_report_e4c_truck_in_sheet",
            "tf_e4c_printouts.action_report_e4c_truck_out_sheet_picking",
            "tf_e4c_printouts.action_report_e4c_dispatch_bol",
            "tf_e4c_printouts.action_report_e4c_dispatch_truck_out_sheet",
            "tf_e4c_printouts.action_report_e4c_export_checklist",
        ]
        for xmlid in report_ids:
            report = self.env.ref(xmlid)
            self.assertEqual(report.report_type, "qweb-pdf")
            self.assertTrue(report.paperformat_id)

    def test_form_buttons_are_loaded(self):
        picking_view = self.env["stock.picking"].get_view(
            view_id=self.env.ref("stock.view_picking_form").id,
            view_type="form",
        )
        self.assertIn("action_e4c_print_receiving_labels", picking_view["arch"])
        self.assertIn("action_e4c_print_truck_in_sheet", picking_view["arch"])
        self.assertIn("action_e4c_print_truck_out_sheet", picking_view["arch"])

        dispatch_view = self.env["tf.dispatch.ticket"].get_view(
            view_id=self.env.ref("tf_container_tracking.view_tf_dispatch_ticket_form").id,
            view_type="form",
        )
        self.assertIn("action_e4c_print_bol", dispatch_view["arch"])
        self.assertIn("action_e4c_print_export_checklist", dispatch_view["arch"])
        etree.fromstring(dispatch_view["arch"].encode())

    def test_button_methods_return_report_actions(self):
        actions = [
            self.picking.action_e4c_print_receiving_labels(),
            self.picking.action_e4c_print_truck_in_sheet(),
            self.picking.action_e4c_print_truck_out_sheet(),
            self.dispatch.action_e4c_print_bol(),
            self.dispatch.action_e4c_print_truck_out_sheet(),
            self.dispatch.action_e4c_print_export_checklist(),
        ]
        for action in actions:
            self.assertEqual(action.get("type"), "ir.actions.report")
            self.assertEqual(action.get("report_type"), "qweb-pdf")

    def test_reports_render_with_expected_data(self):
        report_expectations = {
            "tf_e4c_printouts.report_e4c_receiving_labels": (
                "tf_e4c_printouts.action_report_e4c_receiving_labels",
                ["Container #", "SOPRINT-C01", "Fragile Case"],
            ),
            "tf_e4c_printouts.report_e4c_truck_in_sheet": (
                "tf_e4c_printouts.action_report_e4c_truck_in_sheet",
                ["Truck Sheet", "In", "Fragile Case", "Printout Shipper", "Printout Consignee"],
            ),
            "tf_e4c_printouts.report_e4c_truck_out_sheet_picking": (
                "tf_e4c_printouts.action_report_e4c_truck_out_sheet_picking",
                ["Truck Sheet", "Out", "Fragile Case", "Printout Shipper", "Printout Consignee"],
            ),
            "tf_e4c_printouts.report_e4c_dispatch_bol": (
                "tf_e4c_printouts.action_report_e4c_dispatch_bol",
                ["STRAIGHT BILL OF LADING", "SOPRINT-1 1 of 1", "Printout Shipper", "Printout Consignee", "Bill of Lading Terms"],
            ),
            "tf_e4c_printouts.report_e4c_dispatch_truck_out_sheet": (
                "tf_e4c_printouts.action_report_e4c_dispatch_truck_out_sheet",
                ["Truck Sheet", "Out", "Fragile Case", "Printout Shipper", "Printout Consignee"],
            ),
            "tf_e4c_printouts.report_e4c_export_checklist": (
                "tf_e4c_printouts.action_report_e4c_export_checklist",
                ["EXPORT CHECKLIST", "Load, Block, Brace", "Fragile Case", "Printout Shipper", "Printout Consignee"],
            ),
        }
        picking_reports = {
            "tf_e4c_printouts.report_e4c_receiving_labels",
            "tf_e4c_printouts.report_e4c_truck_in_sheet",
            "tf_e4c_printouts.report_e4c_truck_out_sheet_picking",
        }
        for report_name, (report_xmlid, expected_values) in report_expectations.items():
            record = self.picking if report_name in picking_reports else self.dispatch
            html = self._render_html(report_name, record)
            for expected in expected_values:
                self.assertIn(expected, html)
            pdf_content, output_type = self._render_pdf(report_xmlid, record)
            self.assertEqual(output_type, "pdf")
            self.assertTrue(pdf_content.startswith(b"%PDF"))
            if report_name == "tf_e4c_printouts.report_e4c_dispatch_bol":
                self.assertGreaterEqual(PdfFileReader(BytesIO(pdf_content)).getNumPages(), 2)
