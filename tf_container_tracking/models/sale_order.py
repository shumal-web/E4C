# -*- coding: utf-8 -*-
from datetime import timedelta

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
    tf_dispatch_contact_id = fields.Many2one(
        "res.partner",
        string="Dispatch Contact",
        tracking=True,
        help="Contact person copied to dispatch tickets created from this order.",
    )
    tf_special_instructions = fields.Text(
        string="Special Instructions",
    )
    tf_credit_state = fields.Selection(
        [
            ("active", "Active"),
            ("pending_clear", "Pending 60-Day Clear"),
            ("cleared", "Cleared"),
        ],
        string="E4C Credit Status",
        default="active",
        copy=False,
        tracking=True,
    )
    tf_credit_clear_date = fields.Date(
        string="E4C Credit Clear Date",
        copy=False,
        tracking=True,
    )
    tf_credit_cleared_on = fields.Date(
        string="E4C Credit Cleared On",
        copy=False,
        readonly=True,
    )
    tf_credit_cleared_by_id = fields.Many2one(
        "res.users",
        string="E4C Credit Cleared By",
        copy=False,
        readonly=True,
    )
    tf_partner_credit_limit = fields.Monetary(
        string="Customer E4C Credit Limit",
        currency_field="currency_id",
        compute="_compute_tf_partner_credit_fields",
    )
    tf_partner_credit_used = fields.Monetary(
        string="Customer E4C Credit Used",
        currency_field="currency_id",
        compute="_compute_tf_partner_credit_fields",
    )
    tf_partner_credit_available = fields.Monetary(
        string="Customer E4C Credit Available",
        currency_field="currency_id",
        compute="_compute_tf_partner_credit_fields",
    )
    tf_partner_credit_over_limit = fields.Boolean(
        string="Customer Over E4C Credit Limit",
        compute="_compute_tf_partner_credit_fields",
    )

    @api.depends(
        "partner_id",
        "currency_id",
        "partner_id.tf_credit_limit",
        "partner_id.tf_credit_used",
        "partner_id.tf_credit_available",
        "partner_id.tf_credit_over_limit",
    )
    def _compute_tf_partner_credit_fields(self):
        today = fields.Date.context_today(self)
        for order in self:
            partner = order.partner_id.commercial_partner_id
            if not partner:
                order.tf_partner_credit_limit = 0.0
                order.tf_partner_credit_used = 0.0
                order.tf_partner_credit_available = 0.0
                order.tf_partner_credit_over_limit = False
                continue
            order.tf_partner_credit_limit = partner.currency_id._convert(
                partner.tf_credit_limit,
                order.currency_id,
                order.company_id or self.env.company,
                today,
            )
            order.tf_partner_credit_used = partner.currency_id._convert(
                partner.tf_credit_used,
                order.currency_id,
                order.company_id or self.env.company,
                today,
            )
            order.tf_partner_credit_available = partner.currency_id._convert(
                partner.tf_credit_available,
                order.currency_id,
                order.company_id or self.env.company,
                today,
            )
            order.tf_partner_credit_over_limit = partner.tf_credit_over_limit

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

    def _create_invoices(self, grouped=False, final=False, date=None):
        invoices = super()._create_invoices(grouped=grouped, final=final, date=date)
        self._tf_schedule_credit_clear_for_invoiced()
        return invoices

    def _tf_get_template_default_vals(self, template, vals=None):
        vals = vals or {}
        defaults = {}
        if template and template.exists():
            template_fields = {
                "tf_shipment_type": "tf_shipment_type",
                "tf_address_note": "tf_address_note",
                "tf_special_instructions": "tf_special_instructions",
            }
            for order_field, template_field in template_fields.items():
                value = template[template_field]
                if order_field not in vals and value:
                    defaults[order_field] = value
        return defaults

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            template_id = vals.get("sale_order_template_id")
            if template_id:
                template = self.env["sale.order.template"].browse(template_id)
                vals.update(self._tf_get_template_default_vals(template, vals))
            if vals.get("partner_shipping_id") and not vals.get("tf_dispatch_contact_id"):
                vals["tf_dispatch_contact_id"] = vals["partner_shipping_id"]
            elif vals.get("partner_id") and not vals.get("tf_dispatch_contact_id"):
                vals["tf_dispatch_contact_id"] = vals["partner_id"]
        orders = super().create(vals_list)
        for order, vals in zip(orders, vals_list):
            template = order.sale_order_template_id
            template_defaults = order._tf_get_template_default_vals(template, vals)
            if template_defaults:
                order.write(template_defaults)
            if not order.tf_dispatch_contact_id:
                order.tf_dispatch_contact_id = order.partner_shipping_id or order.partner_id
        return orders

    def write(self, vals):
        if vals.get("sale_order_template_id"):
            template = self.env["sale.order.template"].browse(vals["sale_order_template_id"])
            vals = dict(vals, **self._tf_get_template_default_vals(template, vals))
        if vals.get("partner_shipping_id") and "tf_dispatch_contact_id" not in vals:
            vals = dict(vals, tf_dispatch_contact_id=vals["partner_shipping_id"])
        return super().write(vals)

    @api.onchange("sale_order_template_id")
    def _onchange_sale_order_template_id(self):
        res = super()._onchange_sale_order_template_id()
        for order in self:
            template_defaults = order._tf_get_template_default_vals(order.sale_order_template_id)
            for field_name, value in template_defaults.items():
                order[field_name] = value
            if order.partner_shipping_id and not order.tf_dispatch_contact_id:
                order.tf_dispatch_contact_id = order.partner_shipping_id
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
                    product_template = line.product_id.product_tmpl_id
                    plan_model.create(
                        {
                            "order_id": order.id,
                            "order_line_id": line.id,
                            "sequence": index * 10,
                            "serial_name": seeded_name,
                            "tf_container_number": seeded_name,
                            "tf_internal_status": internal_status,
                            "tf_container_status": "on_water" if order.tf_shipment_type == "import" else "ready",
                            "tf_container_type": product_template.tf_container_type,
                            "tf_import_export": order.tf_shipment_type,
                        }
                    )
                existing.filtered(lambda p: not p.tf_import_export).write({"tf_import_export": order.tf_shipment_type})
                existing.filtered(lambda p: not p.tf_container_type and line.product_id.product_tmpl_id.tf_container_type).write(
                    {"tf_container_type": line.product_id.product_tmpl_id.tf_container_type}
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
        for order in self:
            if order.tf_flow_state != "approved":
                raise UserError(_("Only approved Sales Orders can be completed."))
        self.write({"tf_flow_state": "completed"})
        return True

    def _tf_schedule_credit_clear_for_invoiced(self):
        today = fields.Date.context_today(self)
        clear_date = today + timedelta(days=60)
        to_schedule = self.filtered(
            lambda order: order.state in ("sale", "done")
            and order.invoice_status == "invoiced"
            and order.tf_credit_state != "cleared"
            and not order.tf_credit_clear_date
        )
        if to_schedule:
            to_schedule.write({
                "tf_credit_state": "pending_clear",
                "tf_credit_clear_date": clear_date,
            })
        return True

    def action_tf_clear_credit(self):
        self.write({
            "tf_credit_state": "cleared",
            "tf_credit_clear_date": False,
            "tf_credit_cleared_on": fields.Date.context_today(self),
            "tf_credit_cleared_by_id": self.env.user.id,
        })
        return True

    @api.model
    def _cron_tf_process_customer_credit_limits(self):
        today = fields.Date.context_today(self)
        orders_to_schedule = self.search([
            ("state", "in", ("sale", "done")),
            ("invoice_status", "=", "invoiced"),
            ("tf_credit_state", "!=", "cleared"),
            ("tf_credit_clear_date", "=", False),
        ])
        orders_to_schedule._tf_schedule_credit_clear_for_invoiced()

        orders_to_clear = self.search([
            ("tf_credit_state", "=", "pending_clear"),
            ("tf_credit_clear_date", "!=", False),
            ("tf_credit_clear_date", "<=", today),
        ])
        orders_to_clear.action_tf_clear_credit()
        return True
