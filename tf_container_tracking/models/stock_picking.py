# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tf_container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Tracking",
        index=True,
        readonly=True,
    )
    tf_sale_order_id = fields.Many2one(
        "sale.order",
        string="SO Filter",
        index=True,
        help="Optional sales order context used to filter serial numbers in detailed operations.",
    )
    tf_customer_reference = fields.Char(
        string="Customer Reference",
        related="tf_sale_order_id.client_order_ref",
        readonly=True,
    )
    tf_container_number = fields.Char(
        related="tf_container_plan_id.tf_container_number",
        store=True,
        readonly=True,
        string="Container #",
    )
    tf_flow_kind = fields.Selection(
        [
            ("import_receipt", "Import Receipt"),
            ("import_truck_out", "Import Truck Out"),
            ("case_export_leg_1", "Case Export Leg 1"),
            ("case_export_leg_2", "Case Export Leg 2"),
            ("container_export_leg_3", "Container Export Leg 3"),
            ("direct_container_client", "Direct Container to Client"),
        ],
        string="Flow Kind",
        readonly=True,
        index=True,
    )
    tf_address_note = fields.Text(
        string="SO Address",
        related="tf_sale_order_id.tf_address_note",
        readonly=True,
    )
    tf_shipper_note = fields.Text(
        string="Shipper",
        related="tf_sale_order_id.tf_shipper_note",
        readonly=True,
    )
    tf_consignee_note = fields.Text(
        string="Consignee",
        related="tf_sale_order_id.tf_consignee_note",
        readonly=True,
    )

    @api.onchange("tf_sale_order_id")
    def _onchange_tf_sale_order_id(self):
        for picking in self:
            if picking.tf_sale_order_id:
                picking.origin = picking.tf_sale_order_id.name

    @api.onchange("origin")
    def _onchange_origin_tf_sale_order_id(self):
        for picking in self:
            if picking.tf_sale_order_id or not picking.origin:
                continue
            sale_order = self.env["sale.order"].search([("name", "=", picking.origin)], limit=1)
            if sale_order:
                picking.tf_sale_order_id = sale_order

    @api.model
    def _tf_get_picking_type(self, code, company):
        company = company or self.env.company
        domain = [
            ("code", "=", code),
            ("warehouse_id", "!=", False),
            ("company_id", "=", company.id),
        ]
        picking_type = self.env["stock.picking.type"].search(domain, limit=1)
        if not picking_type:
            picking_type = self.env["stock.picking.type"].with_context(active_test=False).search(domain, limit=1)
        return picking_type

    @api.model
    def _tf_get_container_piece_plans(self, plan):
        piece_plans = plan.tf_piece_plan_ids.filtered(lambda p: not p.tf_is_container_product).sorted(
            lambda p: (p.sequence, p.id)
        )
        if not piece_plans:
            raise UserError("No case/piece serial lines are assigned to this container.")
        return piece_plans

    @api.model
    def _tf_cleanup_placeholder_move_lines(self, picking):
        placeholders = picking.move_line_ids.filtered(
            lambda ml: not ml.lot_id
            and not ml.lot_name
            and not ml.tf_sale_serial_plan_id
            and not ml.quant_id
            and not ml.package_id
            and not ml.result_package_id
            and not ml.owner_id
            and not ml.picked
            and not ml.tf_description
            and not ml.tf_length
            and not ml.tf_width
            and not ml.tf_height
            and not ml.tf_dimension_unit
            and not ml.tf_weight
            and not ml.tf_weight_unit
            and not ml.tf_storage_rate
            and not ml.tf_location_note
        )
        placeholders.unlink()

    @api.model
    def _tf_prepare_piece_move_line_vals(self, move, piece_plan, incoming=False):
        attribute_source = piece_plan.lot_id or piece_plan
        vals = {
            "move_id": move.id,
            "picking_id": move.picking_id.id,
            "company_id": move.picking_id.company_id.id,
            "product_id": move.product_id.id,
            "product_uom_id": move.product_uom.id,
            "location_id": move.location_id.id,
            "location_dest_id": move.location_dest_id.id,
            "quantity": 1.0,
            "tf_sale_serial_plan_id": piece_plan.id,
            "tf_container_plan_id": piece_plan.tf_container_plan_id.id,
            "tf_description": attribute_source.tf_description,
            "tf_length": attribute_source.tf_length,
            "tf_width": attribute_source.tf_width,
            "tf_height": attribute_source.tf_height,
            "tf_dimension_unit": attribute_source.tf_dimension_unit,
            "tf_weight": attribute_source.tf_weight,
            "tf_weight_unit": attribute_source.tf_weight_unit,
            "tf_storage_rate": attribute_source.tf_storage_rate,
            "tf_location_note": attribute_source.tf_location_note,
        }
        if piece_plan.lot_id:
            vals["lot_id"] = piece_plan.lot_id.id
        elif incoming and piece_plan.serial_name:
            vals["lot_name"] = piece_plan.serial_name
        return vals

    @api.model
    def _tf_create_piece_plan_picking(self, plan, picking_type, flow_kind=False):
        piece_plans = self._tf_get_container_piece_plans(plan)
        picking = self.create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "partner_id": plan.order_id.partner_shipping_id.id or plan.order_id.partner_id.id,
                "origin": plan.order_id.name,
                "tf_container_plan_id": plan.id,
                "tf_sale_order_id": plan.order_id.id,
                "tf_flow_kind": flow_kind or False,
            }
        )
        grouped_plans = {}
        move_by_group = {}
        for piece_plan in piece_plans:
            group_key = (
                piece_plan.order_line_id.id,
                piece_plan.product_id.id,
                piece_plan.tf_container_plan_id.id or 0,
            )
            grouped_plans.setdefault(group_key, self.env["tf.sale.serial.plan"])
            grouped_plans[group_key] |= piece_plan

        for (order_line_id, product_id, _container_plan_id), plans_in_group in grouped_plans.items():
            sample_plan = plans_in_group[:1]
            move = self.env["stock.move"].create(
                {
                    "description_picking": sample_plan.product_id.display_name,
                    "picking_id": picking.id,
                    "product_id": product_id,
                    "product_uom": sample_plan.product_id.uom_id.id,
                    "product_uom_qty": float(len(plans_in_group)),
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "sale_line_id": order_line_id,
                }
            )
            move_by_group[(order_line_id, product_id, _container_plan_id)] = move

        picking.action_confirm()

        incoming = picking.picking_type_code == "incoming"
        for piece_plan in piece_plans:
            move = move_by_group[(
                piece_plan.order_line_id.id,
                piece_plan.product_id.id,
                piece_plan.tf_container_plan_id.id or 0,
            )]
            self.env["stock.move.line"].create(
                self._tf_prepare_piece_move_line_vals(move, piece_plan, incoming=incoming)
            )

        self._tf_cleanup_placeholder_move_lines(picking)
        return picking

    @api.model
    def _tf_create_internal_transfer_from_container_plan(self, plan):
        picking_type = self._tf_get_picking_type("internal", plan.company_id)
        if not picking_type:
            raise UserError("No internal picking type found for this company.")
        return self._tf_create_piece_plan_picking(plan, picking_type)

    @api.model
    def _tf_get_or_create_container_lot(self, plan):
        plan.ensure_one()
        if plan.lot_id:
            return plan.lot_id

        lot_name = plan.serial_name or plan.tf_container_number
        if not lot_name:
            raise UserError(_("Container serial is required before creating the truck out transfer."))

        lot = self.env["stock.lot"].search(
            [
                ("name", "=", lot_name),
                ("product_id", "=", plan.product_id.id),
            ],
            limit=1,
        )
        if not lot:
            lot = self.env["stock.lot"].create(
                {
                    "name": lot_name,
                    "product_id": plan.product_id.id,
                    "company_id": plan.company_id.id,
                    "tf_origin_sale_order_id": plan.order_id.id,
                    "tf_description": plan.tf_description,
                    "tf_length": plan.tf_length,
                    "tf_width": plan.tf_width,
                    "tf_height": plan.tf_height,
                    "tf_dimension_unit": plan.tf_dimension_unit,
                    "tf_weight": plan.tf_weight,
                    "tf_weight_unit": plan.tf_weight_unit,
                    "tf_storage_rate": plan.tf_storage_rate,
                    "tf_location_note": plan.tf_location_note,
                    "tf_internal_status": plan.tf_internal_status,
                    "tf_port_to_destuff": plan.tf_port_to_destuff,
                    "tf_container_status": plan.tf_container_status,
                    "tf_container_location": plan.tf_container_location,
                    "tf_eta": plan.tf_eta,
                    "tf_lfd": plan.tf_lfd,
                    "tf_cutoff_date": plan.tf_cutoff_date,
                    "tf_ssl": plan.tf_ssl,
                    "tf_container_type": plan.tf_container_type,
                    "tf_chassis_no": plan.tf_chassis_no,
                    "tf_pubk_no": plan.tf_pubk_no,
                    "tf_import_export": plan.tf_import_export,
                }
            )
        plan.lot_id = lot.id
        return lot

    @api.model
    def _tf_create_export_container_transfer_from_container_plan(self, plan):
        picking_type = self._tf_get_picking_type("internal", plan.company_id)
        if not picking_type:
            raise UserError(_("No internal picking type found for this company."))

        lot = self._tf_get_or_create_container_lot(plan)
        picking = self.create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "partner_id": plan.order_id.partner_shipping_id.id or plan.order_id.partner_id.id,
                "origin": plan.order_id.name,
                "tf_container_plan_id": plan.id,
                "tf_sale_order_id": plan.order_id.id,
                "tf_flow_kind": "container_export_leg_3",
            }
        )
        move = self.env["stock.move"].create(
            {
                "description_picking": plan.product_id.display_name,
                "picking_id": picking.id,
                "product_id": plan.product_id.id,
                "product_uom": plan.product_id.uom_id.id,
                "product_uom_qty": 1.0,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "sale_line_id": plan.order_line_id.id,
            }
        )
        picking.action_confirm()
        self._tf_cleanup_placeholder_move_lines(picking)
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "company_id": picking.company_id.id,
                "product_id": move.product_id.id,
                "product_uom_id": move.product_uom.id,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "quantity": 1.0,
                "lot_id": lot.id,
                "tf_sale_serial_plan_id": plan.id,
                "tf_container_plan_id": plan.id,
                "tf_description": lot.tf_description or plan.tf_description,
                "tf_length": lot.tf_length or plan.tf_length,
                "tf_width": lot.tf_width or plan.tf_width,
                "tf_height": lot.tf_height or plan.tf_height,
                "tf_dimension_unit": lot.tf_dimension_unit or plan.tf_dimension_unit,
                "tf_weight": lot.tf_weight or plan.tf_weight,
                "tf_weight_unit": lot.tf_weight_unit or plan.tf_weight_unit,
                "tf_storage_rate": lot.tf_storage_rate or plan.tf_storage_rate,
                "tf_location_note": lot.tf_location_note or plan.tf_location_note,
            }
        )
        return picking

    @api.model
    def _tf_create_receiving_operation_from_container_plan(self, plan):
        picking_type = self._tf_get_picking_type("incoming", plan.company_id)
        if not picking_type:
            raise UserError("No incoming picking type found for this company.")
        return self._tf_create_piece_plan_picking(plan, picking_type)

    @api.model
    def _tf_create_delivery_order_from_container_plan(self, plan):
        picking_type = self._tf_get_picking_type("outgoing", plan.company_id)
        if not picking_type:
            raise UserError("No delivery picking type found for this company.")
        return self._tf_create_piece_plan_picking(plan, picking_type)

    @api.model
    def _tf_create_direct_delivery_from_container_plan(self, plan):
        picking_type = self._tf_get_picking_type("outgoing", plan.company_id)
        if not picking_type:
            raise UserError(_("No delivery picking type found for this company."))

        piece_plans = plan.tf_piece_plan_ids.filtered(lambda p: not p.tf_is_container_product)
        if piece_plans:
            return self._tf_create_piece_plan_picking(plan, picking_type, flow_kind="direct_container_client")

        lot = self._tf_get_or_create_container_lot(plan)
        picking = self.create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "partner_id": plan.order_id.partner_shipping_id.id or plan.order_id.partner_id.id,
                "origin": plan.order_id.name,
                "tf_container_plan_id": plan.id,
                "tf_sale_order_id": plan.order_id.id,
                "tf_flow_kind": "direct_container_client",
            }
        )
        move = self.env["stock.move"].create(
            {
                "description_picking": plan.product_id.display_name,
                "picking_id": picking.id,
                "product_id": plan.product_id.id,
                "product_uom": plan.product_id.uom_id.id,
                "product_uom_qty": 1.0,
                "location_id": picking.location_id.id,
                "location_dest_id": picking.location_dest_id.id,
                "sale_line_id": plan.order_line_id.id,
            }
        )
        picking.action_confirm()
        self._tf_cleanup_placeholder_move_lines(picking)
        self.env["stock.move.line"].create(
            {
                "move_id": move.id,
                "picking_id": picking.id,
                "company_id": picking.company_id.id,
                "product_id": move.product_id.id,
                "product_uom_id": move.product_uom.id,
                "location_id": move.location_id.id,
                "location_dest_id": move.location_dest_id.id,
                "quantity": 1.0,
                "lot_id": lot.id,
                "tf_sale_serial_plan_id": plan.id,
                "tf_container_plan_id": plan.id,
                "tf_description": lot.tf_description or plan.tf_description,
                "tf_length": lot.tf_length or plan.tf_length,
                "tf_width": lot.tf_width or plan.tf_width,
                "tf_height": lot.tf_height or plan.tf_height,
                "tf_dimension_unit": lot.tf_dimension_unit or plan.tf_dimension_unit,
                "tf_weight": lot.tf_weight or plan.tf_weight,
                "tf_weight_unit": lot.tf_weight_unit or plan.tf_weight_unit,
                "tf_storage_rate": lot.tf_storage_rate or plan.tf_storage_rate,
                "tf_location_note": lot.tf_location_note or plan.tf_location_note,
                "tf_internal_status": plan.tf_internal_status,
                "tf_port_to_destuff": plan.tf_port_to_destuff,
                "tf_container_status": plan.tf_container_status,
                "tf_container_location": plan.tf_container_location,
                "tf_eta": plan.tf_eta,
                "tf_lfd": plan.tf_lfd,
                "tf_cutoff_date": plan.tf_cutoff_date,
                "tf_ssl": plan.tf_ssl,
                "tf_container_type": plan.tf_container_type,
                "tf_chassis_no": plan.tf_chassis_no,
                "tf_pubk_no": plan.tf_pubk_no,
                "tf_import_export": plan.tf_import_export,
            }
        )
        return picking

    @api.model
    def _tf_create_sale_order_lines_picking(self, sale_order, order_lines, operation_code, partner=False, flow_kind=False):
        sale_order.ensure_one()
        if not order_lines:
            raise UserError(_("No sales order lines found for this flow."))
        picking_type = self._tf_get_picking_type(operation_code, sale_order.company_id)
        if not picking_type:
            raise UserError(_("No %s picking type found for this company.") % operation_code)

        picking = self.create(
            {
                "picking_type_id": picking_type.id,
                "location_id": picking_type.default_location_src_id.id,
                "location_dest_id": picking_type.default_location_dest_id.id,
                "partner_id": (partner or sale_order.partner_shipping_id or sale_order.partner_id).id,
                "origin": sale_order.name,
                "tf_sale_order_id": sale_order.id,
                "tf_flow_kind": flow_kind or False,
            }
        )
        for line in order_lines:
            self.env["stock.move"].create(
                {
                    "description_picking": line.product_id.display_name,
                    "picking_id": picking.id,
                    "product_id": line.product_id.id,
                    "product_uom": line.product_uom_id.id,
                    "product_uom_qty": line.product_uom_qty,
                    "location_id": picking.location_id.id,
                    "location_dest_id": picking.location_dest_id.id,
                    "sale_line_id": line.id,
                }
            )
        picking.action_confirm()
        return picking

    def action_tf_truck_out(self):
        self.ensure_one()
        if not self.tf_container_plan_id:
            raise UserError(_("Truck Out can only be used on a container-linked inventory record."))
        return self.tf_container_plan_id.action_truck_out_from_inventory()

    def _tf_prefill_incoming_from_sale_serial_plan(self):
        container_pickings = self.filtered(lambda p: p.picking_type_code == "incoming" and p.tf_container_plan_id)
        other_pickings = self - container_pickings
        res = super(StockPicking, other_pickings)._tf_prefill_incoming_from_sale_serial_plan() if other_pickings else True
        for picking in container_pickings:
            self._tf_cleanup_placeholder_move_lines(picking)
            for move_line in picking.move_line_ids.filtered(lambda ml: ml.tf_sale_serial_plan_id):
                serial_plan = move_line.tf_sale_serial_plan_id
                source = serial_plan.lot_id or serial_plan
                move_line.write(
                    {
                        "lot_name": move_line.lot_name or serial_plan.serial_name or False,
                        "quantity": move_line.quantity or 1.0,
                        "tf_description": source.tf_description,
                        "tf_length": source.tf_length,
                        "tf_width": source.tf_width,
                        "tf_height": source.tf_height,
                        "tf_dimension_unit": source.tf_dimension_unit,
                        "tf_weight": source.tf_weight,
                        "tf_weight_unit": source.tf_weight_unit,
                        "tf_storage_rate": source.tf_storage_rate,
                        "tf_location_note": source.tf_location_note,
                    }
                )
        for picking in self.filtered(lambda p: p.picking_type_code == "incoming"):
            for move_line in picking.move_line_ids.filtered(lambda ml: ml.tf_sale_serial_plan_id):
                serial_plan = move_line.tf_sale_serial_plan_id
                if serial_plan.tf_is_container_product:
                    move_line.write({
                        "tf_internal_status": serial_plan.tf_internal_status,
                        "tf_port_to_destuff": serial_plan.tf_port_to_destuff,
                        "tf_container_status": serial_plan.tf_container_status,
                        "tf_container_location": serial_plan.tf_container_location,
                        "tf_eta": serial_plan.tf_eta,
                        "tf_lfd": serial_plan.tf_lfd,
                        "tf_cutoff_date": serial_plan.tf_cutoff_date,
                        "tf_ssl": serial_plan.tf_ssl,
                        "tf_container_type": serial_plan.tf_container_type,
                        "tf_chassis_no": serial_plan.tf_chassis_no,
                        "tf_pubk_no": serial_plan.tf_pubk_no,
                        "tf_import_export": serial_plan.tf_import_export,
                    })
                if move_line.tf_container_plan_id:
                    continue
                container_plan = serial_plan.tf_container_plan_id
                if container_plan:
                    move_line.tf_container_plan_id = container_plan.id
        return res

    def _tf_prefill_internal_from_sale_serial_plan_lots(self):
        container_pickings = self.filtered(lambda p: p.picking_type_code == "internal" and p.tf_container_plan_id)
        other_pickings = self - container_pickings
        res = super(StockPicking, other_pickings)._tf_prefill_internal_from_sale_serial_plan_lots() if other_pickings else True
        for picking in container_pickings:
            self._tf_cleanup_placeholder_move_lines(picking)
            for move_line in picking.move_line_ids.filtered(
                lambda ml: ml.tf_sale_serial_plan_id and not ml.lot_id and ml.tf_sale_serial_plan_id.lot_id
            ):
                lot = move_line.tf_sale_serial_plan_id.lot_id
                move_line.write(
                    {
                        "lot_id": lot.id,
                        "quantity": 1.0,
                        "tf_description": lot.tf_description,
                        "tf_length": lot.tf_length,
                        "tf_width": lot.tf_width,
                        "tf_height": lot.tf_height,
                        "tf_dimension_unit": lot.tf_dimension_unit,
                        "tf_weight": lot.tf_weight,
                        "tf_weight_unit": lot.tf_weight_unit,
                        "tf_storage_rate": lot.tf_storage_rate,
                        "tf_location_note": lot.tf_location_note,
                    }
                )
        return res

    def _tf_autofill_outgoing_from_internal_done(self, internal_picking):
        container_pickings = self.filtered(lambda p: p.picking_type_code == "outgoing" and p.tf_container_plan_id)
        other_pickings = self - container_pickings
        if other_pickings:
            super(StockPicking, other_pickings)._tf_autofill_outgoing_from_internal_done(internal_picking)

        for picking in container_pickings:
            if picking.location_id.id != internal_picking.location_dest_id.id:
                continue
            self._tf_cleanup_placeholder_move_lines(picking)
            for move_line in picking.move_line_ids.filtered(lambda ml: ml.tf_sale_serial_plan_id and not ml.lot_id):
                internal_line = internal_picking.move_line_ids.filtered(
                    lambda ml: ml.tf_sale_serial_plan_id == move_line.tf_sale_serial_plan_id and ml.lot_id
                )[:1]
                if not internal_line:
                    continue
                lot = internal_line.lot_id
                move_line.write(
                    {
                        "lot_id": lot.id,
                        "quantity": 1.0,
                        "tf_description": lot.tf_description,
                        "tf_length": lot.tf_length,
                        "tf_width": lot.tf_width,
                        "tf_height": lot.tf_height,
                        "tf_dimension_unit": lot.tf_dimension_unit,
                        "tf_weight": lot.tf_weight,
                        "tf_weight_unit": lot.tf_weight_unit,
                        "tf_storage_rate": lot.tf_storage_rate,
                        "tf_location_note": lot.tf_location_note,
                    }
                )

    def _action_done(self):
        res = super()._action_done()
        for picking in self.filtered(lambda p: p.picking_type_code == "incoming"):
            container_plan = picking.tf_container_plan_id
            for move_line in picking.move_line_ids.filtered(lambda ml: ml.product_id.tracking == "serial" and ml.lot_id):
                serial_plan = move_line.tf_sale_serial_plan_id
                is_container_product = bool(move_line.product_id.product_tmpl_id.tf_is_container)
                if serial_plan and serial_plan.order_id:
                    move_line.lot_id.tf_origin_sale_order_id = serial_plan.order_id.id

                if is_container_product:
                    container_vals = {
                        "tf_internal_status": move_line.tf_internal_status,
                        "tf_port_to_destuff": move_line.tf_port_to_destuff,
                        "tf_container_status": move_line.tf_container_status,
                        "tf_container_location": move_line.tf_container_location,
                        "tf_eta": move_line.tf_eta,
                        "tf_lfd": move_line.tf_lfd,
                        "tf_cutoff_date": move_line.tf_cutoff_date,
                        "tf_ssl": move_line.tf_ssl,
                        "tf_container_type": move_line.tf_container_type,
                        "tf_chassis_no": move_line.tf_chassis_no,
                        "tf_pubk_no": move_line.tf_pubk_no,
                        "tf_import_export": move_line.tf_import_export,
                    }
                    move_line.lot_id.write(container_vals)
                    if serial_plan and serial_plan.tf_is_container_product:
                        serial_plan.write(container_vals)

                if serial_plan and move_line.tf_container_plan_id and serial_plan.tf_container_plan_id != move_line.tf_container_plan_id:
                    serial_plan.tf_container_plan_id = move_line.tf_container_plan_id.id

                linked_container_plan = move_line.tf_container_plan_id or (serial_plan.tf_container_plan_id if serial_plan else False)
                if linked_container_plan and linked_container_plan.lot_id:
                    move_line.lot_id.tf_container_lot_id = linked_container_plan.lot_id.id
            if container_plan:
                container_plan.sudo().write(
                    {
                        "tf_container_status": "ready_for_return",
                        "tf_dispatch_progress": "return",
                    }
                )
                return_ticket = container_plan.sudo()._tf_ensure_return_dispatch()
                if not return_ticket.receiving_picking_id:
                    return_ticket.receiving_picking_id = picking.id
        for picking in self.filtered(
            lambda p: p.picking_type_code == "internal" and p.tf_flow_kind == "container_export_leg_3" and p.tf_container_plan_id
        ):
            ticket = picking.tf_container_plan_id.sudo()._ensure_dispatch_ticket("export_container_leg_3")
            if not ticket.internal_transfer_id:
                ticket.internal_transfer_id = picking.id
            if picking.tf_sale_order_id and picking.tf_sale_order_id.tf_flow_state != "completed":
                picking.tf_sale_order_id.tf_flow_state = "completed"
        for picking in self.filtered(
            lambda p: p.picking_type_code == "outgoing" and p.tf_flow_kind == "direct_container_client" and p.tf_container_plan_id
        ):
            plan = picking.tf_container_plan_id.sudo()
            ticket = plan._ensure_dispatch_ticket("direct_container_client")
            if not ticket.delivery_order_id:
                ticket.delivery_order_id = picking.id
            plan.with_context(mail_notrack=True).write(
                {
                    "tf_container_status": "picked_up",
                    "tf_dispatch_progress": "completed",
                }
            )
        return res
