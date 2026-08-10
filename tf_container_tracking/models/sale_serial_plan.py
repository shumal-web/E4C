# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


INTERNAL_STATUS_SELECTION = [
    ("for_approval", "For Approval"),
    ("pickup", "Pickup"),
    ("tracking", "Tracking"),
    ("planning", "Planning"),
    ("dispatch", "Dispatch"),
]

CONTAINER_STATUS_SELECTION = [
    ("on_water", "On the Water"),
    ("at_port", "At Port"),
    ("ready", "Ready"),
    ("ready_for_return", "Ready for Return"),
    ("picked_up", "Picked Up"),
    ("de_stuffed", "De Stuffed"),
    ("returned", "Returned"),
]

DISPATCH_PROGRESS_SELECTION = [
    ("not_dispatched", "Not Dispatched"),
    ("delivery", "Delivery"),
    ("return", "Return"),
    ("completed", "Completed"),
]


class TfSaleSerialPlan(models.Model):
    _name = "tf.sale.serial.plan"
    _inherit = ["tf.sale.serial.plan", "mail.thread", "mail.activity.mixin"]
    _rec_name = "serial_name"
    _rec_names_search = ["serial_name", "tf_container_number", "order_name"]

    serial_name = fields.Char(string="Serial Number", required=False, index=True, tracking=True)

    order_name = fields.Char(related="order_id.name", store=True, readonly=True, index=True)
    tf_is_container_product = fields.Boolean(
        related="product_id.product_tmpl_id.tf_is_container",
        store=True,
        readonly=True,
        index=True,
    )

    tf_container_number = fields.Char(string="Container #", index=True, tracking=True)
    tf_internal_status = fields.Selection(
        INTERNAL_STATUS_SELECTION,
        string="Internal Status",
        default="for_approval",
        index=True,
        tracking=True,
    )
    tf_port_to_destuff = fields.Char(string="Port to De-stuff", index=True, tracking=True)
    tf_container_status = fields.Selection(
        CONTAINER_STATUS_SELECTION,
        string="Container Status",
        default="on_water",
        index=True,
        tracking=True,
    )
    tf_dispatch_progress = fields.Selection(
        DISPATCH_PROGRESS_SELECTION,
        string="Dispatch Progress",
        default="not_dispatched",
        index=True,
        tracking=True,
    )
    tf_ready_on = fields.Datetime(string="Ready On", tracking=True)
    tf_container_location = fields.Char(string="Container Location", index=True, tracking=True)
    tf_eta = fields.Date(string="ETA", index=True, tracking=True)
    tf_lfd = fields.Date(string="LFD", index=True, tracking=True)
    tf_ssl = fields.Char(string="SSL", index=True, tracking=True)
    tf_container_type = fields.Char(string="Type", index=True, tracking=True)
    tf_chassis_no = fields.Char(string="Chassis #", index=True, tracking=True)
    tf_pubk_no = fields.Char(string="PU/BK #", index=True, tracking=True)

    tf_container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Serial",
        ondelete="set null",
        domain="[('order_id', '=', order_id), ('tf_is_container_product', '=', True)]",
        index=True,
        tracking=True,
    )
    tf_piece_plan_ids = fields.One2many(
        "tf.sale.serial.plan",
        "tf_container_plan_id",
        string="Assigned Piece Serials",
    )
    tf_piece_count = fields.Integer(
        string="Assigned Pieces",
        compute="_compute_tf_piece_count",
        store=False,
    )

    @api.depends("tf_piece_plan_ids")
    def _compute_tf_piece_count(self):
        for plan in self:
            plan.tf_piece_count = len(plan.tf_piece_plan_ids)

    @api.constrains("tf_container_plan_id", "tf_is_container_product", "order_id")
    def _check_tf_container_plan_id(self):
        for plan in self:
            container_plan = plan.tf_container_plan_id
            if not container_plan:
                continue
            if plan.tf_is_container_product:
                raise ValidationError(_("Container serial lines cannot be assigned to another container."))
            if container_plan.order_id != plan.order_id:
                raise ValidationError(_("Container serial must belong to the same sales order."))
            if not container_plan.tf_is_container_product:
                raise ValidationError(_("Only container product serials can be selected as container reference."))

    @api.constrains("tf_eta", "tf_lfd")
    def _check_tf_eta_lfd(self):
        for plan in self:
            if plan.tf_eta and plan.tf_lfd and plan.tf_lfd < plan.tf_eta:
                raise ValidationError(_("LFD cannot be before ETA."))

    @api.constrains("tf_container_number", "order_id", "tf_is_container_product")
    def _check_tf_unique_container_number(self):
        for plan in self.filtered(lambda p: p.tf_is_container_product and p.tf_container_number):
            duplicate = self.search(
                [
                    ("id", "!=", plan.id),
                    ("order_id", "=", plan.order_id.id),
                    ("tf_is_container_product", "=", True),
                    ("tf_container_number", "=", plan.tf_container_number),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Container # must be unique within the same sales order. Duplicate found: %s")
                    % plan.tf_container_number
                )

    def name_get(self):
        result = []
        for record in self:
            label = record.serial_name or str(record.id)
            if record.tf_container_number and record.tf_container_number != label:
                label = "%s (%s)" % (label, record.tf_container_number)
            result.append((record.id, label))
        return result

    @api.depends_context("tf_display_container_number")
    @api.depends("serial_name", "tf_container_number", "tf_is_container_product")
    def _compute_display_name(self):
        if not self.env.context.get("tf_display_container_number"):
            return super()._compute_display_name()
        for record in self:
            if record.tf_is_container_product and record.tf_container_number:
                record.display_name = record.tf_container_number
            else:
                record.display_name = record.serial_name or str(record.id)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and not self.env.user.has_group("stock.group_stock_manager"):
            for vals in vals_list:
                if "tf_internal_status" in vals and vals.get("tf_internal_status") not in (False, "for_approval"):
                    raise AccessError(_("Only Inventory Managers can set Internal Status beyond For Approval."))
        records = super().create(vals_list)
        records._tf_apply_ready_dispatch_logic()
        return records

    def _check_tf_internal_status_access(self, target_status):
        if self.env.context.get("tf_auto_internal_status"):
            return
        if not self.env.su and not self.env.user.has_group("stock.group_stock_manager"):
            raise AccessError(_("Only Inventory Managers can change Internal Status."))

        transitions = {
            "for_approval": {"pickup", "tracking", "planning"},
            "pickup": {"tracking", "planning", "dispatch"},
            "tracking": {"for_approval", "pickup", "planning", "dispatch"},
            "planning": {"tracking", "dispatch"},
            "dispatch": {"tracking"},
        }
        label_map = dict(self._fields["tf_internal_status"].selection)

        for record in self:
            current = record.tf_internal_status
            if current == target_status:
                continue
            allowed = transitions.get(current, set())
            if target_status not in allowed:
                raise ValidationError(
                    _("Invalid Internal Status transition: %s -> %s")
                    % (label_map.get(current, current), label_map.get(target_status, target_status))
                )

    def write(self, vals):
        if "tf_internal_status" in vals:
            new_status = vals.get("tf_internal_status")
            changed_records = self.filtered(lambda rec: rec.tf_internal_status != new_status)
            if changed_records:
                changed_records._check_tf_internal_status_access(new_status)
            if new_status == "planning" and "tf_container_status" not in vals:
                vals["tf_container_status"] = "ready"
        res = super().write(vals)
        if any(key in vals for key in ("tf_container_status", "tf_ready_on")):
            self._tf_apply_ready_dispatch_logic()
        return res

    def _tf_apply_ready_dispatch_logic(self):
        for record in self.filtered(
            lambda rec: rec.tf_is_container_product
            and rec.tf_container_status == "ready"
            and rec.order_id.tf_flow_state in ("approved", "completed")
            and rec.order_id.tf_shipment_type != "export"
        ):
            if not record.tf_ready_on:
                super(TfSaleSerialPlan, record.sudo().with_context(mail_notrack=True)).write(
                    {"tf_ready_on": fields.Datetime.now()}
                )
                record.invalidate_recordset(["tf_ready_on"])
            if record.tf_internal_status != "planning":
                super(TfSaleSerialPlan, record.sudo().with_context(tf_auto_internal_status=True)).write(
                    {"tf_internal_status": "planning"}
                )
                record.invalidate_recordset(["tf_internal_status"])
            receive_action = record._tf_ensure_receiving_operation()
            if not receive_action:
                record._tf_ensure_delivery_leg_1()

    def _tf_check_order_approved_for_operations(self):
        for record in self:
            if record.order_id.tf_flow_state not in ("approved", "completed"):
                raise ValidationError(_("Sales Order must be approved before starting container operations."))

    def action_set_for_approval(self):
        self._check_tf_internal_status_access("for_approval")
        self.write({"tf_internal_status": "for_approval"})
        return True

    def action_approve_internal_status(self):
        self._check_tf_internal_status_access("tracking")
        self.write({"tf_internal_status": "tracking"})
        return True

    def action_set_pickup(self):
        self._check_tf_internal_status_access("pickup")
        self.write({"tf_internal_status": "pickup"})
        return True

    def action_set_tracking(self):
        self._check_tf_internal_status_access("tracking")
        self.write({"tf_internal_status": "tracking"})
        return True

    def action_set_dispatch(self):
        self._check_tf_internal_status_access("dispatch")
        self.write({"tf_internal_status": "dispatch"})
        return True
