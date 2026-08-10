# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    tf_shipment_type = fields.Selection(
        [
            ("import", "Import"),
            ("export", "Export"),
        ],
        string="Flow Type",
        default="import",
        tracking=True,
        required=True,
    )
    tf_flow_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("to_approve", "For Approval"),
            ("approved", "Approved"),
            ("completed", "Completed"),
        ],
        string="Flow Status",
        default="draft",
        tracking=True,
        required=True,
    )
    tf_container_tracking_count = fields.Integer(
        compute="_compute_tf_container_tracking_count",
        string="Containers",
    )
    tf_dispatch_ticket_count = fields.Integer(
        compute="_compute_tf_dispatch_ticket_count",
        string="Dispatch Tickets",
    )
    tf_address_note = fields.Text(
        string="Address",
    )
    tf_special_instructions = fields.Text(
        string="Special Instructions",
    )

    def _compute_tf_container_tracking_count(self):
        grouped = self.env["tf.sale.serial.plan"].read_group(
            [
                ("order_id", "in", self.ids),
                ("tf_is_container_product", "=", True),
            ],
            ["order_id"],
            ["order_id"],
        )
        counts = {
            item["order_id"][0]: item["order_id_count"]
            for item in grouped
            if item.get("order_id")
        }
        for order in self:
            order.tf_container_tracking_count = counts.get(order.id, 0)

    def _compute_tf_dispatch_ticket_count(self):
        grouped = self.env["tf.dispatch.ticket"].read_group(
            [("sale_order_id", "in", self.ids)],
            ["sale_order_id"],
            ["sale_order_id"],
        )
        counts = {
            item["sale_order_id"][0]: item["sale_order_id_count"]
            for item in grouped
            if item.get("sale_order_id")
        }
        for order in self:
            order.tf_dispatch_ticket_count = counts.get(order.id, 0)

    def action_open_tf_container_tracking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Container Tracking"),
            "res_model": "tf.sale.serial.plan",
            "view_mode": "list,form",
            "domain": [
                ("order_id", "=", self.id),
                ("tf_is_container_product", "=", True),
            ],
            "context": {
                "search_default_group_order": 1,
            },
            "target": "current",
        }

    def action_open_tf_dispatch_tickets(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Dispatch Tickets"),
            "res_model": "tf.dispatch.ticket",
            "view_mode": "list,form",
            "domain": [("sale_order_id", "=", self.id)],
            "target": "current",
        }

    def action_tf_submit_for_approval(self):
        self.write({"tf_flow_state": "to_approve"})
        return True

    def action_confirm(self):
        res = super().action_confirm()
        self.filtered(lambda order: order.tf_flow_state == "draft").write({"tf_flow_state": "to_approve"})
        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            template_id = vals.get("sale_order_template_id")
            if template_id and "tf_shipment_type" not in vals:
                template = self.env["sale.order.template"].browse(template_id)
                if template.exists() and template.tf_shipment_type:
                    vals["tf_shipment_type"] = template.tf_shipment_type
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            template = order.sale_order_template_id
            if (
                template
                and "tf_shipment_type" not in vals
                and template.tf_shipment_type
                and order.tf_shipment_type != template.tf_shipment_type
            ):
                order.tf_shipment_type = template.tf_shipment_type
        return orders

    def write(self, vals):
        if vals.get("sale_order_template_id") and "tf_shipment_type" not in vals:
            template = self.env["sale.order.template"].browse(vals["sale_order_template_id"])
            if template.exists() and template.tf_shipment_type:
                vals = dict(vals, tf_shipment_type=template.tf_shipment_type)
        return super().write(vals)

    @api.onchange("sale_order_template_id")
    def _onchange_sale_order_template_id(self):
        res = super()._onchange_sale_order_template_id()
        for order in self:
            if order.sale_order_template_id and order.sale_order_template_id.tf_shipment_type:
                order.tf_shipment_type = order.sale_order_template_id.tf_shipment_type
        return res

    def _tf_has_direct_container_to_client_flow(self):
        for order in self:
            if any(order.order_line.mapped("product_id.product_tmpl_id.tf_direct_container_to_client")):
                return True
        return False

    def _tf_container_seed(self, index):
        self.ensure_one()
        order_name = (self.name or "SO").replace("/", "-").replace(" ", "")
        return f"{order_name}-C{index:02d}"

    def _tf_get_container_lines(self):
        self.ensure_one()
        return self.order_line.filtered(lambda l: l.product_id.product_tmpl_id.tf_is_container)

    def _tf_get_case_lines(self):
        self.ensure_one()
        return self.order_line.filtered(
            lambda l: not l.product_id.product_tmpl_id.tf_is_container
            and not l.product_id.product_tmpl_id.tf_direct_container_to_client
        )

    def _tf_ensure_container_plans_from_order(self, internal_status):
        plan_model = self.env["tf.sale.serial.plan"]
        for order in self:
            for line in order._tf_get_container_lines():
                existing = line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
                target = int(line.product_uom_qty or 0)
                if len(existing) >= target:
                    missing = self.env["tf.sale.serial.plan"]
                else:
                    missing = range(len(existing) + 1, target + 1)
                for index in missing:
                    seeded_name = order._tf_container_seed(index)
                    plan_model.create(
                        {
                            "order_id": order.id,
                            "order_line_id": line.id,
                            "sequence": index * 10,
                            "serial_name": seeded_name,
                            "tf_container_number": seeded_name,
                            "tf_internal_status": internal_status,
                            "tf_container_status": "on_water" if order.tf_shipment_type == "import" else "ready",
                        }
                    )
                existing.filtered(lambda p: p.tf_internal_status != internal_status).with_context(
                    tf_auto_internal_status=True
                ).write({"tf_internal_status": internal_status})

    def action_tf_approve(self):
        for order in self:
            target_status = "tracking" if order.tf_shipment_type == "import" else "pickup"
            order._tf_ensure_container_plans_from_order(target_status)
            order.tf_flow_state = "approved"
            order.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")._tf_apply_ready_dispatch_logic()
        return True

    def _tf_create_order_dispatch_ticket(self, dispatch_type, title, location_note=False):
        self.ensure_one()
        existing = self.env["tf.dispatch.ticket"].search(
            [
                ("sale_order_id", "=", self.id),
                ("dispatch_type", "=", dispatch_type),
                ("container_plan_id", "=", False),
                ("state", "!=", "cancel"),
            ],
            limit=1,
        )
        if existing:
            return existing
        return self.env["tf.dispatch.ticket"].create(
            {
                "sale_order_id": self.id,
                "dispatch_type": dispatch_type,
                "location_partner_id": self.partner_shipping_id.id or self.partner_id.id,
                "location_note": location_note or self.partner_shipping_id.display_name or self.partner_id.display_name,
                "note": title,
            }
        )

    def action_tf_create_export_flow(self):
        for order in self:
            if order.tf_shipment_type != "export":
                raise UserError(_("Export flow can only be created for Sales Orders with Flow Type = Export."))
            if order.tf_flow_state != "approved":
                raise UserError(_("Sales Order must be approved before creating export flow."))

            case_lines = order._tf_get_case_lines()
            if case_lines:
                incoming = self.env["stock.picking"]._tf_create_sale_order_lines_picking(
                    order,
                    case_lines,
                    "incoming",
                    partner=order.partner_id,
                    flow_kind="case_export_leg_1",
                )
                port_transfer = self.env["stock.picking"]._tf_create_sale_order_lines_picking(
                    order,
                    case_lines,
                    "internal",
                    partner=order.partner_shipping_id or order.partner_id,
                    flow_kind="case_export_leg_2",
                )
                leg_1 = order._tf_create_order_dispatch_ticket("export_case_leg_1", _("Case Export Pickup Leg 1"))
                leg_2 = order._tf_create_order_dispatch_ticket("export_case_leg_2", _("Case Export Pickup Leg 2"), location_note="Port")
                if not leg_1.receiving_picking_id:
                    leg_1.receiving_picking_id = incoming.id
                if not leg_2.internal_transfer_id:
                    leg_2.internal_transfer_id = port_transfer.id

            for container_plan in order.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product"):
                container_plan._ensure_dispatch_ticket("export_container_leg_1")
                container_plan._ensure_dispatch_ticket("export_container_leg_2")
        return True

    def action_tf_mark_flow_completed(self):
        self.write({"tf_flow_state": "completed"})
        return True
