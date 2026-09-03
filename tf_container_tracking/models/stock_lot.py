# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

from .sale_serial_plan import (
    INTERNAL_STATUS_SELECTION,
    CONTAINER_STATUS_SELECTION,
    ORIGIN_SELECTION,
    SSL_SELECTION,
    normalize_tf_container_selection_values,
)


class StockLot(models.Model):
    _inherit = "stock.lot"

    tf_origin_sale_order_id = fields.Many2one(
        "sale.order",
        string="Source Sales Order",
        index=True,
        readonly=True,
    )
    tf_customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="tf_origin_sale_order_id.partner_id",
        store=True,
        readonly=True,
    )

    tf_is_container_lot = fields.Boolean(
        related="product_id.product_tmpl_id.tf_is_container",
        readonly=True,
    )
    tf_container_lot_id = fields.Many2one(
        "stock.lot",
        string="Container Number",
        ondelete="set null",
        index=True,
    )
    tf_internal_status = fields.Selection(
        INTERNAL_STATUS_SELECTION,
        string="Internal Status",
        default="for_approval",
    )
    tf_port_to_destuff = fields.Selection(ORIGIN_SELECTION, string="Origin")
    tf_container_status = fields.Selection(
        CONTAINER_STATUS_SELECTION,
        string="Container Status",
        default="on_water",
    )
    tf_container_location = fields.Char(string="Container Location")
    tf_eta = fields.Date(string="ETA")
    tf_lfd = fields.Date(string="LFD")
    tf_cutoff_date = fields.Date(string="Cutoff")
    tf_ssl = fields.Selection(SSL_SELECTION, string="SSL")
    tf_container_type = fields.Char(string="Type")
    tf_chassis_no = fields.Char(string="Chassis #")
    tf_pubk_no = fields.Char(string="PU/BK #")
    tf_import_export = fields.Selection(
        [
            ("import", "Import"),
            ("export", "Export"),
        ],
        string="Import/Export",
    )

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([normalize_tf_container_selection_values(dict(vals)) for vals in vals_list])

    def write(self, vals):
        return super().write(normalize_tf_container_selection_values(dict(vals)))

    @api.constrains("tf_container_lot_id")
    def _check_tf_container_lot_id(self):
        for lot in self:
            if not lot.tf_container_lot_id:
                continue
            if lot.tf_container_lot_id == lot:
                raise ValidationError(_("A lot cannot be assigned as its own container."))
            if not lot.tf_container_lot_id.product_id.product_tmpl_id.tf_is_container:
                raise ValidationError(_("Selected container lot must belong to a container product."))

    def _tf_get_sale_serial_plan(self):
        self.ensure_one()
        return self.env["tf.sale.serial.plan"].search([("lot_id", "=", self.id)], limit=1)

    def _tf_get_container_plan_for_truck_out(self):
        self.ensure_one()
        serial_plan = self._tf_get_sale_serial_plan()
        if serial_plan:
            if serial_plan.tf_is_container_product:
                return serial_plan
            if serial_plan.tf_container_plan_id:
                return serial_plan.tf_container_plan_id
        if self.tf_container_lot_id:
            return self.tf_container_lot_id._tf_get_container_plan_for_truck_out()
        return self.env["tf.sale.serial.plan"]

    def _tf_get_on_hand_quant_for_truck_out(self):
        self.ensure_one()
        return self.env["stock.quant"].search(
            [
                ("lot_id", "=", self.id),
                ("product_id", "=", self.product_id.id),
                ("location_id.usage", "=", "internal"),
                ("quantity", ">", 0),
            ],
            order="quantity desc, id desc",
            limit=1,
        )

    def _tf_find_existing_truck_out_picking(self, sale_orders):
        lot_ids = set(self.ids)
        candidate_lines = self.env["stock.move.line"].search(
            [
                ("lot_id", "in", list(lot_ids)),
                ("picking_id.picking_type_code", "=", "internal"),
                ("picking_id.tf_sale_order_id", "in", sale_orders.ids),
                ("picking_id.state", "not in", ("done", "cancel")),
            ]
        )
        for picking in candidate_lines.mapped("picking_id"):
            picking_lot_ids = set(picking.move_line_ids.filtered("lot_id").mapped("lot_id").ids)
            if picking_lot_ids == lot_ids:
                return picking
        return self.env["stock.picking"]

    def _tf_prepare_truck_out_dispatch_note(self, container_plans, sale_orders=False):
        lot_names = ", ".join(self.mapped("name"))
        so_names = ", ".join((sale_orders or self.mapped("tf_origin_sale_order_id")).mapped("name"))
        if len(container_plans) == 1:
            return _("Truck Out created from Inventory W/Stock.\nSales Orders: %(orders)s\nSelected Serials: %(lots)s") % {
                "orders": so_names,
                "lots": lot_names,
            }
        if container_plans:
            container_labels = ", ".join(
                [plan.tf_container_number or plan.serial_name or str(plan.id) for plan in container_plans]
            )
            return _(
                "Truck Out created from Inventory W/Stock.\nSales Orders: %(orders)s\nSelected Serials: %(lots)s\nContainers: %(containers)s"
            ) % {
                "orders": so_names,
                "lots": lot_names,
                "containers": container_labels,
            }
        return _("Truck Out created from Inventory W/Stock.\nSales Orders: %(orders)s\nSelected Serials: %(lots)s") % {
            "orders": so_names,
            "lots": lot_names,
        }

    def _tf_create_truck_out_transfer(self, sale_orders, source_location, dest_location):
        sale_order = sale_orders[:1]
        picking_type = self.env["stock.picking"]._tf_get_picking_type("internal", sale_order.company_id)
        if not picking_type:
            raise UserError(_("No internal picking type found for this company."))

        container_plans = self.env["tf.sale.serial.plan"]
        for lot in self:
            container_plans |= lot._tf_get_container_plan_for_truck_out()
        picking_container = container_plans[:1] if len(container_plans) == 1 else self.env["tf.sale.serial.plan"]
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": dest_location.id,
                "partner_id": sale_order.partner_shipping_id.id or sale_order.partner_id.id,
                "origin": ", ".join(sale_orders.mapped("name")),
                "tf_sale_order_id": sale_order.id,
                "tf_container_plan_id": picking_container.id or False,
                "tf_flow_kind": "import_truck_out" if picking_container else False,
            }
        )

        grouped_lots = defaultdict(lambda: self.env["stock.lot"])
        lot_to_serial_plan = {}
        lot_to_container_plan = {}
        for lot in self.sorted(lambda rec: rec.id):
            serial_plan = lot._tf_get_sale_serial_plan()
            container_plan = lot._tf_get_container_plan_for_truck_out()
            group_key = (lot.product_id.id, container_plan.id or 0)
            grouped_lots[group_key] |= lot
            lot_to_serial_plan[lot.id] = serial_plan
            lot_to_container_plan[lot.id] = container_plan

        move_by_group = {}
        for (product_id, container_plan_id), lots in grouped_lots.items():
            sample_lot = lots[:1]
            serial_plan = lot_to_serial_plan.get(sample_lot.id)
            move = self.env["stock.move"].create(
                {
                    "description_picking": sample_lot.product_id.display_name,
                    "picking_id": picking.id,
                    "product_id": product_id,
                    "product_uom": sample_lot.product_id.uom_id.id,
                    "product_uom_qty": float(len(lots)),
                    "location_id": source_location.id,
                    "location_dest_id": dest_location.id,
                    "sale_line_id": serial_plan.order_line_id.id if serial_plan else False,
                }
            )
            move_by_group[(product_id, container_plan_id)] = move

        picking.action_confirm()

        for lot in self.sorted(lambda rec: rec.id):
            container_plan = lot_to_container_plan.get(lot.id)
            serial_plan = lot_to_serial_plan.get(lot.id)
            move = move_by_group[(lot.product_id.id, container_plan.id or 0)]
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "company_id": picking.company_id.id,
                    "product_id": lot.product_id.id,
                    "product_uom_id": lot.product_id.uom_id.id,
                    "location_id": source_location.id,
                    "location_dest_id": dest_location.id,
                    "quantity": 1.0,
                    "lot_id": lot.id,
                    "tf_sale_serial_plan_id": serial_plan.id if serial_plan else False,
                    "tf_container_plan_id": container_plan.id or False,
                    "tf_description": lot.tf_description,
                    "tf_length": lot.tf_length,
                    "tf_width": lot.tf_width,
                    "tf_height": lot.tf_height,
                    "tf_dimension_unit": lot.tf_dimension_unit,
                    "tf_weight": lot.tf_weight,
                    "tf_weight_unit": lot.tf_weight_unit,
                    "tf_storage_rate": lot.tf_storage_rate,
                    "tf_location_note": lot.tf_location_note,
                    "tf_internal_status": container_plan.tf_internal_status if container_plan else "for_approval",
                    "tf_port_to_destuff": container_plan.tf_port_to_destuff if container_plan else False,
                    "tf_container_status": container_plan.tf_container_status if container_plan else "on_water",
                    "tf_container_location": container_plan.tf_container_location if container_plan else False,
                    "tf_eta": container_plan.tf_eta if container_plan else False,
                    "tf_lfd": container_plan.tf_lfd if container_plan else False,
                    "tf_cutoff_date": container_plan.tf_cutoff_date if container_plan else False,
                    "tf_ssl": container_plan.tf_ssl if container_plan else False,
                    "tf_container_type": container_plan.tf_container_type if container_plan else False,
                    "tf_chassis_no": container_plan.tf_chassis_no if container_plan else False,
                    "tf_pubk_no": container_plan.tf_pubk_no if container_plan else False,
                    "tf_import_export": container_plan.tf_import_export if container_plan else False,
                }
            )

        self.env["stock.picking"]._tf_cleanup_placeholder_move_lines(picking)
        return picking

    def _tf_create_truck_out_delivery(self, sale_orders, source_location, dest_location):
        sale_order = sale_orders[:1]
        picking_type = self.env["stock.picking"]._tf_get_picking_type("outgoing", sale_order.company_id)
        if not picking_type:
            raise UserError(_("No delivery picking type found for this company."))

        container_plans = self.env["tf.sale.serial.plan"]
        for lot in self:
            container_plans |= lot._tf_get_container_plan_for_truck_out()
        picking_container = container_plans[:1] if len(container_plans) == 1 else self.env["tf.sale.serial.plan"]
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": source_location.id,
                "location_dest_id": dest_location.id,
                "partner_id": sale_order.partner_shipping_id.id or sale_order.partner_id.id,
                "origin": ", ".join(sale_orders.mapped("name")),
                "tf_sale_order_id": sale_order.id,
                "tf_container_plan_id": picking_container.id or False,
                "tf_flow_kind": "import_truck_out" if picking_container else False,
            }
        )

        grouped_lots = defaultdict(lambda: self.env["stock.lot"])
        lot_to_serial_plan = {}
        lot_to_container_plan = {}
        for lot in self.sorted(lambda rec: rec.id):
            serial_plan = lot._tf_get_sale_serial_plan()
            container_plan = lot._tf_get_container_plan_for_truck_out()
            grouped_lots[(lot.product_id.id, container_plan.id or 0)] |= lot
            lot_to_serial_plan[lot.id] = serial_plan
            lot_to_container_plan[lot.id] = container_plan

        move_by_group = {}
        for (product_id, container_plan_id), lots in grouped_lots.items():
            sample_lot = lots[:1]
            serial_plan = lot_to_serial_plan.get(sample_lot.id)
            move = self.env["stock.move"].create(
                {
                    "description_picking": sample_lot.product_id.display_name,
                    "picking_id": picking.id,
                    "product_id": product_id,
                    "product_uom": sample_lot.product_id.uom_id.id,
                    "product_uom_qty": float(len(lots)),
                    "location_id": source_location.id,
                    "location_dest_id": dest_location.id,
                    "sale_line_id": serial_plan.order_line_id.id if serial_plan else False,
                }
            )
            move_by_group[(product_id, container_plan_id)] = move

        picking.action_confirm()
        for lot in self.sorted(lambda rec: rec.id):
            container_plan = lot_to_container_plan.get(lot.id)
            serial_plan = lot_to_serial_plan.get(lot.id)
            move = move_by_group[(lot.product_id.id, container_plan.id or 0)]
            self.env["stock.move.line"].create(
                {
                    "move_id": move.id,
                    "picking_id": picking.id,
                    "company_id": picking.company_id.id,
                    "product_id": lot.product_id.id,
                    "product_uom_id": lot.product_id.uom_id.id,
                    "location_id": source_location.id,
                    "location_dest_id": dest_location.id,
                    "quantity": 1.0,
                    "lot_id": lot.id,
                    "tf_sale_serial_plan_id": serial_plan.id if serial_plan else False,
                    "tf_container_plan_id": container_plan.id or False,
                    "tf_description": lot.tf_description,
                    "tf_length": lot.tf_length,
                    "tf_width": lot.tf_width,
                    "tf_height": lot.tf_height,
                    "tf_dimension_unit": lot.tf_dimension_unit,
                    "tf_weight": lot.tf_weight,
                    "tf_weight_unit": lot.tf_weight_unit,
                    "tf_storage_rate": lot.tf_storage_rate,
                    "tf_location_note": lot.tf_location_note,
                    "tf_internal_status": container_plan.tf_internal_status if container_plan else "for_approval",
                    "tf_port_to_destuff": container_plan.tf_port_to_destuff if container_plan else False,
                    "tf_container_status": container_plan.tf_container_status if container_plan else "on_water",
                    "tf_container_location": container_plan.tf_container_location if container_plan else False,
                    "tf_eta": container_plan.tf_eta if container_plan else False,
                    "tf_lfd": container_plan.tf_lfd if container_plan else False,
                    "tf_cutoff_date": container_plan.tf_cutoff_date if container_plan else False,
                    "tf_ssl": container_plan.tf_ssl if container_plan else False,
                    "tf_container_type": container_plan.tf_container_type if container_plan else False,
                    "tf_chassis_no": container_plan.tf_chassis_no if container_plan else False,
                    "tf_pubk_no": container_plan.tf_pubk_no if container_plan else False,
                    "tf_import_export": container_plan.tf_import_export if container_plan else False,
                }
            )
        self.env["stock.picking"]._tf_cleanup_placeholder_move_lines(picking)
        return picking

    def action_tf_truck_out_selected(self):
        lots = self.exists()
        if not lots:
            raise UserError(_("Please select at least one serial number."))

        sale_orders = lots.mapped("tf_origin_sale_order_id")
        if any(not lot.tf_origin_sale_order_id for lot in lots):
            raise UserError(_("Every selected serial must be linked to a Sales Order."))
        customers = sale_orders.mapped("partner_id.commercial_partner_id")
        if len(customers) != 1:
            raise UserError(_("Please select serials for the same customer."))
        sale_order = sale_orders.sorted(lambda order: (order.name or "", order.id))[:1]

        source_locations = self.env["stock.location"]
        for lot in lots:
            quant = lot._tf_get_on_hand_quant_for_truck_out()
            if not quant:
                raise UserError(
                    _("Selected serial %(serial)s is not available in internal stock.")
                    % {"serial": lot.display_name}
                )
            source_locations |= quant.location_id

        if len(source_locations) != 1:
            raise UserError(_("Please select serials from the same source location."))

        picking_type = self.env["stock.picking"]._tf_get_picking_type("internal", sale_order.company_id)
        if not picking_type:
            raise UserError(_("No internal picking type found for this company."))

        existing_picking = lots._tf_find_existing_truck_out_picking(sale_orders)
        if existing_picking:
            dispatch_ticket = self.env["tf.dispatch.ticket"].search(
                [
                    ("internal_transfer_id", "=", existing_picking.id),
                    ("state", "!=", "cancel"),
                ],
                limit=1,
            )
            if dispatch_ticket:
                return {
                    "type": "ir.actions.act_window",
                    "name": _("Dispatch Ticket"),
                    "res_model": "tf.dispatch.ticket",
                    "res_id": dispatch_ticket.id,
                    "view_mode": "form",
                    "target": "current",
                }
            return {
                "type": "ir.actions.act_window",
                "name": _("Internal Transfer"),
                "res_model": "stock.picking",
                "res_id": existing_picking.id,
                "view_mode": "form",
                "target": "current",
            }

        picking = lots._tf_create_truck_out_transfer(
            sale_orders,
            source_locations[:1],
            picking_type.default_location_dest_id,
        )
        outgoing_type = self.env["stock.picking"]._tf_get_picking_type("outgoing", sale_order.company_id)
        if not outgoing_type:
            raise UserError(_("No delivery picking type found for this company."))
        delivery = lots._tf_create_truck_out_delivery(
            sale_orders,
            picking.location_dest_id,
            outgoing_type.default_location_dest_id,
        )

        container_plans = self.env["tf.sale.serial.plan"]
        for lot in lots:
            container_plans |= lot._tf_get_container_plan_for_truck_out()
        if container_plans:
            active_plans = container_plans.filtered(lambda plan: plan.tf_dispatch_progress == "not_dispatched")
            if active_plans:
                active_plans.sudo().with_context(mail_notrack=True).write({"tf_dispatch_progress": "delivery"})

        dispatch_ticket = self.env["tf.dispatch.ticket"].create(
            {
                "dispatch_type": "import_dispatch",
                "sale_order_id": sale_order.id,
                "sale_order_ids": [(6, 0, sale_orders.ids)],
                "container_plan_id": container_plans[:1].id if len(container_plans) == 1 else False,
                "location_partner_id": sale_order.partner_shipping_id.id or sale_order.partner_id.id,
                "location_note": source_locations[:1].display_name,
                "dispatch_date": fields.Datetime.now(),
                "internal_transfer_id": picking.id,
                "delivery_order_id": delivery.id or False,
                "note": lots._tf_prepare_truck_out_dispatch_note(container_plans, sale_orders),
            }
        )

        return {
            "type": "ir.actions.act_window",
            "name": _("Dispatch Ticket"),
            "res_model": "tf.dispatch.ticket",
            "res_id": dispatch_ticket.id,
            "view_mode": "form",
            "target": "current",
        }
