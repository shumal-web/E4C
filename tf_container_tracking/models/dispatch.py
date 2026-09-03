# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TfDispatchTruck(models.Model):
    _name = "tf.dispatch.truck"
    _description = "Dispatch Truck"
    _rec_name = "name"

    name = fields.Char(required=True, index=True)
    plate_no = fields.Char(string="Plate #", index=True)
    active = fields.Boolean(default=True)
    note = fields.Char()


class TfDispatchDriver(models.Model):
    _name = "tf.dispatch.driver"
    _description = "Dispatch Driver"
    _rec_name = "name"

    name = fields.Char(required=True, index=True)
    phone = fields.Char()
    active = fields.Boolean(default=True)
    note = fields.Char()


class TfDispatchTrailer(models.Model):
    _name = "tf.dispatch.trailer"
    _description = "Dispatch Trailer"
    _rec_name = "name"

    name = fields.Char(required=True, index=True)
    current_location = fields.Char()
    destination_location = fields.Char()
    active = fields.Boolean(default=True)
    note = fields.Char()
    dispatch_ticket_ids = fields.One2many("tf.dispatch.ticket", "trailer_id", string="Dispatch Tickets")


class TfDispatchTicket(models.Model):
    _name = "tf.dispatch.ticket"
    _description = "Dispatch Ticket"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "dispatch_date desc, id desc"

    name = fields.Char(default="New", copy=False, readonly=True, index=True)
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)

    dispatch_type = fields.Selection(
        [
            ("pickup_parts", "Pickup Parts"),
            ("return_container", "Return Container"),
            ("delivery_leg_1", "Delivery Leg 1"),
            ("delivery_leg_2", "Delivery Leg 2"),
            ("return_leg", "Return Dispatch"),
            ("export_case_leg_1", "Case Export Leg 1"),
            ("export_case_leg_2", "Case Export Leg 2"),
            ("export_container_leg_1", "Container Export Leg 1"),
            ("export_container_leg_2", "Container Export Leg 2"),
            ("export_container_leg_3", "Container Export Leg 3"),
            ("direct_container_client", "Direct Container to Client"),
            ("cfs_piece_pickup_leg_1", "CFS Pieces Pickup Leg 1"),
            ("cfs_piece_delivery_leg_2", "CFS Pieces Delivery Leg 2"),
            ("import_dispatch", "Import Dispatch"),
            ("standalone", "Standalone"),
        ],
        default="pickup_parts",
        required=True,
        tracking=True,
    )
    sale_order_id = fields.Many2one("sale.order", required=True, index=True, tracking=True)
    sale_order_ids = fields.Many2many(
        "sale.order",
        "tf_dispatch_ticket_sale_order_rel",
        "dispatch_ticket_id",
        "sale_order_id",
        string="Sales Orders",
        help="Additional Sales Orders included on the same truck-out dispatch.",
    )
    customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="sale_order_id.partner_id",
        store=True,
        readonly=True,
    )
    contact_id = fields.Many2one("res.partner", string="Contact", tracking=True)
    customer_reference = fields.Char(
        string="Customer Reference",
        related="sale_order_id.client_order_ref",
        readonly=True,
    )
    container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container",
        domain="[('order_id', '=', sale_order_id), ('tf_is_container_product', '=', True)]",
        tracking=True,
    )
    container_number = fields.Char(
        string="Container Number",
        compute="_compute_container_number",
        store=True,
        readonly=True,
    )
    location_partner_id = fields.Many2one("res.partner", string="Location", tracking=True)
    location_note = fields.Char(string="Dispatch Address", tracking=True)

    truck_id = fields.Many2one("tf.dispatch.truck", tracking=True)
    driver_id = fields.Many2one("tf.dispatch.driver", tracking=True)
    trailer_id = fields.Many2one("tf.dispatch.trailer", tracking=True)
    trailer_current_location = fields.Char(string="Trailer Current Location", tracking=True)
    trailer_destination_location = fields.Char(string="Trailer Destination", tracking=True)

    whatsapp_sent = fields.Boolean(tracking=True)
    whatsapp_sent_on = fields.Datetime(readonly=True)
    whatsapp_sent_by = fields.Many2one("res.users", readonly=True)

    dispatch_date = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    completed = fields.Boolean(compute="_compute_completed", store=True)
    completed_on = fields.Datetime(readonly=True)
    completed_by = fields.Many2one("res.users", readonly=True)
    note = fields.Text()

    internal_transfer_id = fields.Many2one("stock.picking", string="Internal Transfer", readonly=True)
    delivery_order_id = fields.Many2one("stock.picking", string="Delivery Order", readonly=True)
    receiving_picking_id = fields.Many2one("stock.picking", string="Receiving Operation", readonly=True)
    tf_address_note = fields.Text(
        string="Address",
        related="sale_order_id.tf_address_note",
        readonly=True,
    )
    tf_shipper_note = fields.Text(
        string="Shipper",
        related="sale_order_id.tf_shipper_note",
        readonly=True,
    )
    tf_consignee_note = fields.Text(
        string="Consignee",
        related="sale_order_id.tf_consignee_note",
        readonly=True,
    )
    tf_origin = fields.Selection(
        string="Origin",
        related="container_plan_id.tf_port_to_destuff",
        store=True,
        readonly=True,
    )
    tf_ssl = fields.Selection(
        string="SSL",
        related="container_plan_id.tf_ssl",
        store=True,
        readonly=True,
    )
    tf_cutoff_date = fields.Date(
        string="Cutoff",
        related="container_plan_id.tf_cutoff_date",
        store=True,
        readonly=True,
    )
    tf_container_type = fields.Char(
        string="Type",
        related="container_plan_id.tf_container_type",
        store=True,
        readonly=True,
    )
    tf_pubk_no = fields.Char(
        string="PU/BK #",
        related="container_plan_id.tf_pubk_no",
        store=True,
        readonly=True,
    )
    tf_container_weight = fields.Float(
        string="Weight",
        related="container_plan_id.tf_weight",
        store=True,
        readonly=True,
    )
    tf_container_weight_unit = fields.Selection(
        related="container_plan_id.tf_weight_unit",
        store=True,
        readonly=True,
    )
    tf_import_export = fields.Selection(
        related="container_plan_id.tf_import_export",
        store=True,
        readonly=True,
        string="Import/Export",
    )

    whatsapp_message_preview = fields.Text(
        string="WhatsApp Message Preview",
        compute="_compute_whatsapp_message_preview",
    )

    @api.depends("container_plan_id", "container_plan_id.tf_container_number", "container_plan_id.serial_name")
    def _compute_container_number(self):
        for rec in self:
            rec.container_number = (
                rec.container_plan_id.tf_container_number
                or rec.container_plan_id.serial_name
                or False
            )

    @api.depends("state")
    def _compute_completed(self):
        for rec in self:
            rec.completed = rec.state == "completed"

    @api.depends(
        "sale_order_id",
        "sale_order_ids",
        "customer_id",
        "contact_id",
        "container_plan_id",
        "dispatch_date",
        "trailer_destination_location",
        "customer_reference",
        "tf_origin",
        "tf_ssl",
        "tf_cutoff_date",
        "tf_container_type",
        "tf_pubk_no",
        "tf_import_export",
    )
    def _compute_whatsapp_message_preview(self):
        for rec in self:
            sales_orders = rec.sale_order_ids or rec.sale_order_id
            so = ", ".join(sales_orders.mapped("name")) or "-"
            customer = rec.customer_id.display_name or "-"
            contact = rec.contact_id.display_name or "-"
            customer_ref = rec.customer_reference or "-"
            container = rec.container_number or "-"
            when = fields.Datetime.to_string(rec.dispatch_date) if rec.dispatch_date else "-"
            trailer_destination = rec.trailer_destination_location or rec.location_note or "-"
            cutoff = fields.Date.to_string(rec.tf_cutoff_date) if rec.tf_cutoff_date else "-"
            import_export_label = {
                "import": _("Import"),
                "export": _("Export"),
            }.get(rec.tf_import_export, "-")
            rec.whatsapp_message_preview = _(
                "Dispatch Instruction\n"
                "SO: %(so)s\n"
                "Customer: %(customer)s\n"
                "Contact: %(contact)s\n"
                "Customer Reference: %(customer_ref)s\n"
                "Container: %(container)s\n"
                "Type: %(container_type)s\n"
                "PU/BK #: %(pubk_no)s\n"
                "SSL: %(ssl)s\n"
                "Cutoff: %(cutoff)s\n"
                "Origin: %(origin)s\n"
                "Import/Export: %(import_export)s\n"
                "Destination: %(trailer_destination)s\n"
                "Date: %(when)s"
            ) % {
                "so": so,
                "customer": customer,
                "contact": contact,
                "customer_ref": customer_ref,
                "container": container,
                "container_type": rec.tf_container_type or "-",
                "pubk_no": rec.tf_pubk_no or "-",
                "ssl": rec.tf_ssl or "-",
                "cutoff": cutoff,
                "origin": rec.tf_origin or "-",
                "import_export": import_export_label,
                "trailer_destination": trailer_destination,
                "when": when,
            }

    @api.onchange("sale_order_id")
    def _onchange_sale_order_id(self):
        for rec in self:
            if rec.sale_order_id and not rec.location_partner_id:
                rec.location_partner_id = rec.sale_order_id.partner_shipping_id
            if rec.sale_order_id and not rec.contact_id:
                rec.contact_id = rec.sale_order_id.tf_dispatch_contact_id or rec.sale_order_id.partner_shipping_id or rec.sale_order_id.partner_id
            if rec.sale_order_id and not rec.sale_order_ids:
                rec.sale_order_ids = rec.sale_order_id

    @api.onchange("trailer_id")
    def _onchange_trailer_id(self):
        for rec in self:
            if rec.trailer_id and not rec.trailer_current_location:
                rec.trailer_current_location = rec.trailer_id.current_location
            if rec.trailer_id and not rec.trailer_destination_location:
                rec.trailer_destination_location = rec.location_note or rec.location_partner_id.display_name or rec.trailer_id.destination_location

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = sequence.next_by_code("tf.dispatch.ticket") or "New"
            sale_order = self.env["sale.order"].browse(vals.get("sale_order_id")).exists()
            if sale_order:
                vals.setdefault("contact_id", (sale_order.tf_dispatch_contact_id or sale_order.partner_shipping_id or sale_order.partner_id).id)
                if not vals.get("sale_order_ids"):
                    vals["sale_order_ids"] = [(6, 0, sale_order.ids)]
        return super().create(vals_list)

    def action_send_whatsapp(self):
        for rec in self:
            rec.write(
                {
                    "whatsapp_sent": True,
                    "whatsapp_sent_on": fields.Datetime.now(),
                    "whatsapp_sent_by": self.env.user.id,
                    "state": "sent" if rec.state == "draft" else rec.state,
                }
            )
        return True

    def action_mark_in_progress(self):
        for rec in self:
            if rec.state not in ("draft", "sent"):
                continue
            rec.state = "in_progress"
        return True

    def action_complete(self):
        follow_up_action = False
        for rec in self:
            if rec.state == "completed":
                continue
            if not rec.trailer_id:
                raise UserError(_("Trailer is required before completing dispatch."))
            rec.write(
                {
                    "state": "completed",
                    "completed_on": fields.Datetime.now(),
                    "completed_by": self.env.user.id,
                }
            )
            if rec.trailer_id:
                if rec.trailer_destination_location:
                    rec.trailer_id.write(
                        {
                            "current_location": rec.trailer_destination_location,
                            "destination_location": False,
                        }
                    )
                elif rec.trailer_current_location:
                    rec.trailer_id.current_location = rec.trailer_current_location
            next_action = rec._tf_handle_completion_follow_up()
            if len(self) == 1 and next_action:
                follow_up_action = next_action
        return follow_up_action or True

    def _tf_handle_completion_follow_up(self):
        self.ensure_one()
        if self.dispatch_type == "delivery_leg_1" and self.container_plan_id:
            plan = self.container_plan_id.sudo()
            leg_2 = plan._tf_ensure_delivery_leg_2()
            vals = {}
            if self.trailer_id and not leg_2.trailer_id:
                vals["trailer_id"] = self.trailer_id.id
            if self.truck_id and not leg_2.truck_id:
                vals["truck_id"] = self.truck_id.id
            if self.driver_id and not leg_2.driver_id:
                vals["driver_id"] = self.driver_id.id
            if self.trailer_destination_location and not leg_2.trailer_current_location:
                vals["trailer_current_location"] = self.trailer_destination_location
            if vals:
                leg_2.write(vals)
            return {
                "type": "ir.actions.act_window",
                "name": _("Dispatch Ticket"),
                "res_model": "tf.dispatch.ticket",
                "res_id": leg_2.id,
                "view_mode": "form",
                "target": "current",
            }
        if self.dispatch_type == "cfs_piece_pickup_leg_1" and self.sale_order_id:
            leg_2 = self.sale_order_id._tf_ensure_cfs_pieces_flow()[1]
            vals = {}
            if self.trailer_id and not leg_2.trailer_id:
                vals["trailer_id"] = self.trailer_id.id
            if self.truck_id and not leg_2.truck_id:
                vals["truck_id"] = self.truck_id.id
            if self.driver_id and not leg_2.driver_id:
                vals["driver_id"] = self.driver_id.id
            if self.trailer_destination_location and not leg_2.trailer_current_location:
                vals["trailer_current_location"] = self.trailer_destination_location
            if vals:
                leg_2.write(vals)
            return {
                "type": "ir.actions.act_window",
                "name": _("Dispatch Ticket"),
                "res_model": "tf.dispatch.ticket",
                "res_id": leg_2.id,
                "view_mode": "form",
                "target": "current",
            }
        if self.dispatch_type in ("return_leg", "return_container") and self.container_plan_id:
            plan = self.container_plan_id
            super(TfSaleSerialPlan, plan.sudo().with_context(mail_notrack=True)).write(
                {
                    "tf_container_status": "returned",
                    "tf_dispatch_progress": "completed",
                }
            )
        elif self.dispatch_type == "export_container_leg_3" and self.sale_order_id:
            self.sale_order_id.sudo().write({"tf_flow_state": "completed"})
        elif self.dispatch_type == "direct_container_client" and self.container_plan_id:
            plan = self.container_plan_id
            super(TfSaleSerialPlan, plan.sudo().with_context(mail_notrack=True)).write(
                {
                    "tf_container_status": "picked_up",
                    "tf_dispatch_progress": "completed",
                }
            )

    def action_cancel(self):
        self.write({"state": "cancel"})
        return True

    def action_reset_to_draft(self):
        self.write({"state": "draft"})
        return True

    def action_open_internal_transfer(self):
        self.ensure_one()
        if not self.internal_transfer_id:
            raise UserError(_("No linked internal transfer on this dispatch ticket."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.internal_transfer_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_delivery_order(self):
        self.ensure_one()
        if not self.delivery_order_id:
            raise UserError(_("No linked delivery order on this dispatch ticket."))
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.delivery_order_id.id,
            "view_mode": "form",
            "target": "current",
        }


class TfSaleSerialPlan(models.Model):
    _inherit = "tf.sale.serial.plan"

    tf_dispatch_ticket_ids = fields.One2many("tf.dispatch.ticket", "container_plan_id", string="Dispatch Ticket Lines")
    tf_dispatch_ticket_count = fields.Integer(compute="_compute_tf_dispatch_ticket_count", string="Dispatch Count")
    tf_linked_picking_count = fields.Integer(compute="_compute_tf_linked_picking_count", string="Inventory Docs")

    @api.depends("tf_dispatch_ticket_ids")
    def _compute_tf_dispatch_ticket_count(self):
        for rec in self:
            rec.tf_dispatch_ticket_count = len(rec.tf_dispatch_ticket_ids)

    def _compute_tf_linked_picking_count(self):
        picking_data = self.env["stock.picking"].read_group(
            [("tf_container_plan_id", "in", self.ids)],
            ["tf_container_plan_id"],
            ["tf_container_plan_id"],
        )
        counts = {
            item["tf_container_plan_id"][0]: item["tf_container_plan_id_count"]
            for item in picking_data
            if item.get("tf_container_plan_id")
        }
        for rec in self:
            rec.tf_linked_picking_count = counts.get(rec.id, 0)

    def action_open_dispatch_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dispatch Tickets"),
            "res_model": "tf.dispatch.ticket",
            "view_mode": "list,form",
            "domain": [("container_plan_id", "=", self.id)],
            "context": {
                "default_sale_order_id": self.order_id.id,
                "default_container_plan_id": self.id,
            },
            "target": "current",
        }

    def action_open_linked_pickings(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Inventory Documents"),
            "res_model": "stock.picking",
            "view_mode": "list,form",
            "domain": [("tf_container_plan_id", "=", self.id)],
            "context": {
                "default_tf_container_plan_id": self.id,
                "default_tf_sale_order_id": self.order_id.id,
            },
            "target": "current",
        }

    def action_tf_copy_container_numbers(self):
        containers = self.filtered("tf_is_container_product")
        numbers = [
            value
            for value in containers.mapped(lambda rec: rec.tf_container_number or rec.serial_name)
            if value
        ]
        if not numbers:
            raise UserError(_("No container numbers found on the selected records."))
        return {
            "type": "ir.actions.client",
            "tag": "tf_container_tracking.copy_to_clipboard",
            "params": {
                "text": "\n".join(numbers),
                "message": _("%s container number(s) copied.") % len(numbers),
            },
        }

    def action_tf_open_bulk_update_wizard(self):
        containers = self.filtered("tf_is_container_product")
        if not containers:
            raise UserError(_("Please select at least one container tracking record."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Bulk Update Containers"),
            "res_model": "tf.container.bulk.update.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": "tf.sale.serial.plan",
                "active_ids": containers.ids,
            },
        }

    def _tf_get_assignment_order_line(self):
        self.ensure_one()
        candidate_lines = self.order_id.order_line.filtered(
            lambda line: (
                line.product_id.tracking == "serial"
                and not line.product_id.product_tmpl_id.tf_is_container
                and line.product_id.product_tmpl_id.tf_requires_container
            )
        )
        if not candidate_lines:
            return False

        assigned_lines = candidate_lines.filtered(
            lambda line: any(plan.tf_container_plan_id == self for plan in line.tf_serial_plan_ids)
        )
        if assigned_lines:
            return assigned_lines.sorted(lambda line: line.sequence or line.id)[:1]

        unplanned_lines = candidate_lines.filtered(lambda line: not line.tf_serial_plan_ids)
        if unplanned_lines:
            return unplanned_lines.sorted(lambda line: line.sequence or line.id)[:1]

        return candidate_lines.sorted(lambda line: line.sequence or line.id)[:1]

    def _tf_open_assignment_wizard(self):
        self.ensure_one()
        order_line = self._tf_get_assignment_order_line()
        if not order_line:
            return False
        wizard = self.env["tf.sale.serial.wizard"].with_context(default_order_line_id=order_line.id).create({})
        return {
            "type": "ir.actions.act_window",
            "name": _("Serial Details"),
            "res_model": "tf.sale.serial.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _prepare_dispatch_defaults(self, dispatch_type):
        self.ensure_one()
        location_note = self.tf_port_to_destuff or self.tf_container_location
        dispatch_date = self.tf_ready_on or fields.Datetime.now()
        if dispatch_type in ("delivery_leg_2", "export_container_leg_2"):
            location_note = self.tf_container_location or self.tf_container_number or location_note
        if dispatch_type == "direct_container_client":
            location_note = (
                self.order_id.partner_shipping_id.display_name
                or self.order_id.partner_id.display_name
                or location_note
            )
        return {
            "default_dispatch_type": dispatch_type,
            "default_sale_order_id": self.order_id.id,
            "default_container_plan_id": self.id,
            "default_location_partner_id": self.order_id.partner_shipping_id.id or self.order_id.partner_id.id,
            "default_location_note": location_note,
            "default_dispatch_date": dispatch_date,
            "default_trailer_destination_location": location_note,
            "default_contact_id": (self.order_id.tf_dispatch_contact_id or self.order_id.partner_shipping_id or self.order_id.partner_id).id,
        }

    def _prepare_dispatch_create_vals(self, dispatch_type):
        defaults = self._prepare_dispatch_defaults(dispatch_type)
        return {
            "dispatch_type": defaults["default_dispatch_type"],
            "sale_order_id": defaults["default_sale_order_id"],
            "container_plan_id": defaults["default_container_plan_id"],
            "location_partner_id": defaults["default_location_partner_id"],
            "location_note": defaults["default_location_note"],
            "dispatch_date": defaults["default_dispatch_date"],
            "trailer_destination_location": defaults["default_trailer_destination_location"],
            "contact_id": defaults.get("default_contact_id"),
            "sale_order_ids": [(6, 0, [defaults["default_sale_order_id"]])],
        }

    def _get_existing_dispatch_ticket(self, dispatch_type, active_only=True):
        self.ensure_one()
        domain = [
            ("sale_order_id", "=", self.order_id.id),
            ("container_plan_id", "=", self.id),
            ("dispatch_type", "=", dispatch_type),
        ]
        if active_only:
            domain.append(("state", "not in", ("completed", "cancel")))
        else:
            domain.append(("state", "!=", "cancel"))
        return self.env["tf.dispatch.ticket"].search(domain, limit=1)

    def _ensure_dispatch_ticket(self, dispatch_type):
        self.ensure_one()
        existing = self._get_existing_dispatch_ticket(dispatch_type, active_only=False)
        if existing:
            return existing
        vals = self._prepare_dispatch_create_vals(dispatch_type)
        return self.env["tf.dispatch.ticket"].create(vals)

    def _tf_ensure_delivery_leg_1(self):
        self.ensure_one()
        ticket = self._ensure_dispatch_ticket("delivery_leg_1")
        if self.tf_dispatch_progress == "not_dispatched":
            super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "delivery"})
        return ticket

    def _tf_ensure_delivery_leg_2(self):
        self.ensure_one()
        ticket = self._ensure_dispatch_ticket("delivery_leg_2")
        if self.tf_dispatch_progress == "not_dispatched":
            super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "delivery"})
        return ticket

    def _tf_ensure_export_container_leg_1(self):
        self.ensure_one()
        return self._ensure_dispatch_ticket("export_container_leg_1")

    def _tf_ensure_export_container_leg_2(self):
        self.ensure_one()
        return self._ensure_dispatch_ticket("export_container_leg_2")

    def _tf_ensure_export_container_leg_3(self):
        self.ensure_one()
        return self._ensure_dispatch_ticket("export_container_leg_3")

    def _tf_ensure_return_dispatch(self):
        self.ensure_one()
        ticket = self._ensure_dispatch_ticket("return_leg")
        super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "return"})
        return ticket

    def _tf_ensure_direct_container_client_flow(self):
        self.ensure_one()
        ticket = self._ensure_dispatch_ticket("direct_container_client")
        delivery_action = self._open_existing_picking_or_create(
            "outgoing",
            _("Direct Delivery Order"),
            "_tf_create_direct_delivery_from_container_plan",
        )
        delivery = self.env["stock.picking"].browse(delivery_action.get("res_id"))
        if delivery and not ticket.delivery_order_id:
            ticket.delivery_order_id = delivery.id
        if self.tf_dispatch_progress == "not_dispatched":
            super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "delivery"})
        return delivery_action

    def action_undo_ready_dispatch_receiving(self):
        if not self.env.user.has_group("stock.group_stock_manager"):
            raise UserError(_("Only inventory managers can undo Ready dispatch/receiving."))
        for plan in self:
            if not plan.tf_is_container_product:
                raise UserError(_("Undo Ready can only be used on container records."))
            if plan.tf_container_status not in ("ready", "picked_up") and plan.tf_dispatch_progress != "delivery":
                raise UserError(_("This container is not in a Ready delivery state."))

            dispatch_tickets = self.env["tf.dispatch.ticket"].search(
                [
                    ("container_plan_id", "=", plan.id),
                    ("dispatch_type", "in", ("delivery_leg_1", "delivery_leg_2", "direct_container_client")),
                    ("state", "!=", "cancel"),
                ]
            )
            if dispatch_tickets.filtered(lambda ticket: ticket.state == "completed"):
                raise UserError(_("Ready cannot be undone because a linked dispatch ticket is already completed."))

            linked_pickings = self.env["stock.picking"].search(
                [
                    ("tf_container_plan_id", "=", plan.id),
                    ("picking_type_code", "in", ("incoming", "internal", "outgoing")),
                    ("state", "!=", "cancel"),
                ]
            )
            linked_pickings |= dispatch_tickets.mapped("receiving_picking_id")
            linked_pickings |= dispatch_tickets.mapped("internal_transfer_id")
            linked_pickings |= dispatch_tickets.mapped("delivery_order_id")
            linked_pickings = linked_pickings.exists()
            if linked_pickings.filtered(lambda picking: picking.state == "done"):
                raise UserError(
                    _("Ready cannot be undone because a linked receiving or transfer document is already done.")
                )

            draft_pickings = linked_pickings.filtered(lambda picking: picking.state == "draft")
            active_pickings = linked_pickings - draft_pickings
            if active_pickings:
                active_pickings.action_cancel()
            if draft_pickings:
                draft_pickings.unlink()
            if dispatch_tickets:
                dispatch_tickets.action_cancel()

            reset_values = {
                "tf_container_status": "at_port" if plan.order_id.tf_shipment_type == "import" else "ready",
                "tf_dispatch_progress": "not_dispatched",
                "tf_ready_on": False,
            }
            if plan.order_id.tf_shipment_type == "import":
                reset_values["tf_internal_status"] = "tracking"
            super(TfSaleSerialPlan, plan.sudo().with_context(mail_notrack=True)).write(reset_values)
        return True

    def _open_existing_dispatch_or_create(self, dispatch_type, title):
        self.ensure_one()
        existing = self._get_existing_dispatch_ticket(dispatch_type, active_only=False)
        if existing:
            return {
                "type": "ir.actions.act_window",
                "name": _("Dispatch Ticket"),
                "res_model": "tf.dispatch.ticket",
                "res_id": existing.id,
                "view_mode": "form",
                "target": "current",
            }
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "tf.dispatch.ticket",
            "res_id": self._ensure_dispatch_ticket(dispatch_type).id,
            "view_mode": "form",
            "target": "current",
        }

    def action_create_pickup_dispatch_ticket(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        return self._open_existing_dispatch_or_create("pickup_parts", _("Create Pickup Dispatch"))

    def action_create_return_dispatch_ticket(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        return self._open_existing_dispatch_or_create("return_container", _("Create Return Container Dispatch"))

    def _tf_ensure_receiving_operation(self):
        self.ensure_one()
        if not self.tf_piece_plan_ids.filtered(lambda plan: not plan.tf_is_container_product):
            return False
        receive_action = self._open_existing_picking_or_create(
            "incoming",
            _("Receiving Operation"),
            "_tf_create_receiving_operation_from_container_plan",
        )
        ticket = self._tf_ensure_delivery_leg_1()
        if receive_action.get("res_id") and not ticket.receiving_picking_id:
            ticket.receiving_picking_id = receive_action["res_id"]
        return receive_action

    def action_receive_container(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        if self.order_id._tf_has_direct_container_to_client_flow():
            if self.tf_container_status != "ready":
                self.write({"tf_container_status": "ready"})
                self.invalidate_recordset(["tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])
            return self._tf_ensure_direct_container_client_flow()

        if self.tf_container_status != "ready":
            self.write({"tf_container_status": "ready"})
            self.invalidate_recordset(["tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])

        receive_action = self._tf_ensure_receiving_operation()
        if not receive_action:
            assignment_action = self._tf_open_assignment_wizard()
            if assignment_action:
                return assignment_action
            raise UserError(_("No case/piece serial lines are assigned to this container."))
        if self.tf_dispatch_progress == "not_dispatched":
            super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "delivery"})
        return receive_action

    def action_truck_out_from_inventory(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        if self.order_id._tf_has_direct_container_to_client_flow():
            if self.tf_container_status != "ready":
                self.write({"tf_container_status": "ready"})
                self.invalidate_recordset(["tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])
            return self._tf_ensure_direct_container_client_flow()

        if self.order_id.tf_shipment_type == "export":
            internal_action = self._open_existing_picking_or_create(
                "internal",
                _("Truck Out Transfer"),
                "_tf_create_export_container_transfer_from_container_plan",
            )
            internal = self.env["stock.picking"].browse(internal_action["res_id"])
            if not internal.tf_flow_kind:
                internal.tf_flow_kind = "container_export_leg_3"
            ticket = self._tf_ensure_export_container_leg_3()
            if not ticket.internal_transfer_id:
                ticket.internal_transfer_id = internal.id
            return internal_action

        if self.tf_container_status != "ready":
            self.write({"tf_container_status": "ready"})
            self.invalidate_recordset(["tf_internal_status", "tf_dispatch_progress", "tf_ready_on"])

        if not self.tf_piece_plan_ids.filtered(lambda plan: not plan.tf_is_container_product):
            assignment_action = self._tf_open_assignment_wizard()
            if assignment_action:
                return assignment_action

        internal_action = self._open_existing_picking_or_create(
            "internal",
            _("Truck Out Transfer"),
            "_tf_create_internal_transfer_from_container_plan",
        )
        internal = self.env["stock.picking"].browse(internal_action["res_id"])
        if not internal.tf_flow_kind:
            internal.tf_flow_kind = "import_truck_out"
        ticket = self._tf_ensure_delivery_leg_1()
        if not ticket.internal_transfer_id:
            ticket.internal_transfer_id = internal.id
        if self.tf_dispatch_progress == "not_dispatched":
            super(TfSaleSerialPlan, self.sudo().with_context(mail_notrack=True)).write({"tf_dispatch_progress": "delivery"})
        return internal_action

    def _open_existing_picking_or_create(self, operation_code, title, create_method_name):
        self.ensure_one()
        picking_type = self.env["stock.picking"]._tf_get_picking_type(operation_code, self.company_id)
        if not picking_type:
            raise UserError(_("No %s picking type found for this company.") % operation_code)
        picking_domain = [
            ("picking_type_id", "=", picking_type.id),
            ("origin", "=", self.order_id.name),
            ("tf_container_plan_id", "=", self.id),
            ("state", "!=", "cancel"),
        ]
        existing = self.env["stock.picking"].search(picking_domain, order="id desc", limit=1)
        if existing:
            self._tf_prepare_existing_picking(existing)
            return {
                "type": "ir.actions.act_window",
                "name": title,
                "res_model": "stock.picking",
                "res_id": existing.id,
                "view_mode": "form",
                "target": "current",
            }

        create_method = getattr(self.env["stock.picking"], create_method_name)
        picking = create_method(self)
        self._tf_prepare_existing_picking(picking)
        return {
            "type": "ir.actions.act_window",
            "name": title,
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def _tf_prepare_existing_picking(self, picking):
        picking.ensure_one()
        if picking.picking_type_code == "incoming":
            picking._tf_prefill_incoming_from_sale_serial_plan()
        elif picking.picking_type_code == "internal":
            picking._tf_prefill_internal_from_sale_serial_plan_lots()
        elif picking.picking_type_code == "outgoing" and self.order_id.name:
            internal_pickings = self.env["stock.picking"].search(
                [
                    ("picking_type_code", "=", "internal"),
                    ("origin", "=", self.order_id.name),
                    ("state", "=", "done"),
                ],
                order="date_done desc, id desc",
                limit=1,
            )
            if internal_pickings:
                picking._tf_autofill_outgoing_from_internal_done(internal_pickings)

    def action_create_internal_transfer(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        return self._open_existing_picking_or_create(
            "internal",
            _("Internal Transfer"),
            "_tf_create_internal_transfer_from_container_plan",
        )

    def action_create_delivery_order(self):
        self.ensure_one()
        self._tf_check_order_approved_for_operations()
        if self.order_id._tf_has_direct_container_to_client_flow():
            return self._tf_ensure_direct_container_client_flow()
        return self._open_existing_picking_or_create(
            "outgoing",
            _("Delivery Order"),
            "_tf_create_delivery_order_from_container_plan",
        )

    def action_deliver_to_client(self):
        return self.action_truck_out_from_inventory()
