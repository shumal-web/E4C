# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


INTERNAL_STATUS_SELECTION = [
    ("for_approval", "For Approval"),
    ("hold", "Hold"),
    ("hold_ssl", "Hold SSL"),
    ("hold_cbsa", "Hold CBSA"),
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

SSL_SELECTION = [
    ("CMA CGM", "CMA CGM"),
    ("MSC", "MSC"),
    ("HAPAG-LLOYD", "HAPAG-LLOYD"),
    ("MAERSK", "MAERSK"),
    ("ONE", "ONE"),
    ("ZIM", "ZIM"),
    ("EVERGREEN", "EVERGREEN"),
    ("COSCO", "COSCO"),
    ("HMM", "HMM"),
    ("YANG MING MARINE", "YANG MING MARINE"),
]

ORIGIN_SELECTION = [
    ("mgt section 77", "mgt section 77"),
    ("mgt section 62", "mgt section 62"),
    ("Termont Viau 52", "Termont Viau 52"),
    ("Termont Maisonneuve 68", "Termont Maisonneuve 68"),
    ("CN", "CN"),
    ("CP", "CP"),
]

SSL_VALUE_MAP = dict(SSL_SELECTION)
SSL_VALUE_MAP.update(
    {
        "CMA-CGM": "CMA CGM",
        "cma cgm": "CMA CGM",
        "msc": "MSC",
        "hapag-lloyd": "HAPAG-LLOYD",
        "maersk": "MAERSK",
        "one": "ONE",
        "zim": "ZIM",
        "evergreen": "EVERGREEN",
        "cosco": "COSCO",
        "hmm": "HMM",
        "yang ming marine": "YANG MING MARINE",
    }
)
ORIGIN_VALUE_MAP = dict(ORIGIN_SELECTION)
ORIGIN_VALUE_MAP.update(
    {
        "MGT Section 77": "mgt section 77",
        "MGT Section 62": "mgt section 62",
        "mgt 77": "mgt section 77",
        "mgt 62": "mgt section 62",
    }
)


def normalize_tf_container_selection_values(vals):
    """Keep legacy free-text values from crashing new selection fields."""
    if vals.get("tf_ssl"):
        vals["tf_ssl"] = SSL_VALUE_MAP.get(vals["tf_ssl"], False)
    if vals.get("tf_port_to_destuff"):
        vals["tf_port_to_destuff"] = ORIGIN_VALUE_MAP.get(vals["tf_port_to_destuff"], False)
    return vals

DISPATCH_PROGRESS_SELECTION = [
    ("not_dispatched", "Not Dispatched"),
    ("delivery", "Delivery"),
    ("return", "Return"),
    ("completed", "Completed"),
]

WEIGHT_UNIT_SELECTION = [("g", "g"), ("kg", "kg"), ("lb", "lb")]
WEIGHT_TO_KG = {"g": 0.001, "kg": 1.0, "lb": 0.45359237}


def convert_weight(value, from_unit, to_unit):
    value = value or 0.0
    from_unit = from_unit or to_unit
    to_unit = to_unit or from_unit
    if not value or not from_unit or not to_unit or from_unit == to_unit:
        return value
    if from_unit not in WEIGHT_TO_KG or to_unit not in WEIGHT_TO_KG:
        return value
    return value * WEIGHT_TO_KG[from_unit] / WEIGHT_TO_KG[to_unit]


def format_tf_partner_address(partner):
    if not partner:
        return False
    values = [partner.display_name]
    address = partner._display_address(without_company=True)
    if address:
        values.append(address)
    return "\n".join(dict.fromkeys([value for value in values if value]))


class TfSaleSerialPlan(models.Model):
    _name = "tf.sale.serial.plan"
    _inherit = ["tf.sale.serial.plan", "mail.thread", "mail.activity.mixin"]
    _rec_name = "serial_name"
    _rec_names_search = ["serial_name", "tf_container_number", "tf_container_serial_number", "order_name"]

    serial_name = fields.Char(string="File Number", required=False, index=True, tracking=True)

    order_name = fields.Char(related="order_id.name", store=True, readonly=True, index=True)
    tf_customer_id = fields.Many2one(
        "res.partner",
        string="Customer",
        related="order_id.partner_id",
        store=True,
        readonly=True,
        index=True,
    )
    tf_is_container_product = fields.Boolean(
        related="product_id.product_tmpl_id.tf_is_container",
        store=True,
        readonly=True,
        index=True,
    )

    tf_container_number = fields.Char(string="Container #", index=True, tracking=True)
    tf_container_serial_number = fields.Char(
        string="Container Serial Number",
        index=True,
        tracking=True,
        help="Real carrier/container serial number. The File Number remains the internal E4C tracking reference.",
    )
    tf_internal_status = fields.Selection(
        INTERNAL_STATUS_SELECTION,
        string="Internal Status",
        default="for_approval",
        index=True,
        tracking=True,
    )
    tf_port_to_destuff = fields.Selection(
        ORIGIN_SELECTION,
        string="Origin",
        index=True,
        tracking=True,
    )
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
    tf_cutoff_date = fields.Date(string="Cutoff", index=True, tracking=True)
    tf_ssl = fields.Selection(
        SSL_SELECTION,
        string="SSL",
        index=True,
        tracking=True,
    )
    tf_container_type = fields.Char(string="Type", index=True, tracking=True)
    tf_chassis_no = fields.Char(string="Chassis #", index=True, tracking=True)
    tf_pubk_no = fields.Char(string="PU/BK #", index=True, tracking=True)
    tf_import_export = fields.Selection(
        [
            ("import", "Import"),
            ("export", "Export"),
        ],
        string="Import/Export",
        index=True,
        tracking=True,
    )
    tf_address_note = fields.Text(
        string="Address Snapshot",
        tracking=True,
        help="Address snapshot used for this container or piece serial.",
    )
    tf_address_partner_id = fields.Many2one(
        "res.partner",
        string="Address",
        index=True,
        tracking=True,
        help="Selected address/contact. The text snapshot is kept separately for old records and printouts.",
    )
    tf_weight = fields.Float(string="Tare / Piece Weight")
    tf_total_weight = fields.Float(
        string="Total Weight",
        compute="_compute_tf_total_weight",
        store=True,
        help="For containers, this is tare weight plus the weight of all linked pieces.",
    )
    tf_total_weight_unit = fields.Selection(
        WEIGHT_UNIT_SELECTION,
        string="Total Weight Unit",
        compute="_compute_tf_total_weight",
        store=True,
    )
    tf_shipper_partner_id = fields.Many2one(
        "res.partner",
        string="Shipper Address",
        related="order_id.tf_shipper_partner_id",
        store=True,
        readonly=True,
    )
    tf_shipper_note = fields.Text(
        string="Shipper",
        related="order_id.tf_shipper_note",
        store=True,
        readonly=True,
    )
    tf_consignee_partner_id = fields.Many2one(
        "res.partner",
        string="Consignee Address",
        related="order_id.tf_consignee_partner_id",
        store=True,
        readonly=True,
    )
    tf_consignee_note = fields.Text(
        string="Consignee",
        related="order_id.tf_consignee_note",
        store=True,
        readonly=True,
    )
    tf_eta_overdue = fields.Boolean(compute="_compute_tf_overdue_dates")
    tf_lfd_overdue = fields.Boolean(compute="_compute_tf_overdue_dates")

    tf_container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Number",
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

    @api.depends(
        "tf_is_container_product",
        "tf_weight",
        "tf_weight_unit",
        "tf_piece_plan_ids.tf_weight",
        "tf_piece_plan_ids.tf_weight_unit",
    )
    def _compute_tf_total_weight(self):
        for plan in self:
            if not plan.tf_is_container_product:
                plan.tf_total_weight = plan.tf_weight or 0.0
                plan.tf_total_weight_unit = plan.tf_weight_unit or False
                continue

            piece_plans = plan.tf_piece_plan_ids.filtered(lambda piece: not piece.tf_is_container_product)
            first_piece_unit = next((piece.tf_weight_unit for piece in piece_plans if piece.tf_weight_unit), False)
            total_unit = plan.tf_weight_unit or first_piece_unit or "kg"
            total = convert_weight(plan.tf_weight, plan.tf_weight_unit or total_unit, total_unit)
            for piece in piece_plans:
                total += convert_weight(piece.tf_weight, piece.tf_weight_unit or total_unit, total_unit)
            plan.tf_total_weight = total
            plan.tf_total_weight_unit = total_unit

    @api.depends("tf_eta", "tf_lfd", "tf_dispatch_progress")
    def _compute_tf_overdue_dates(self):
        today = fields.Date.context_today(self)
        for plan in self:
            active = plan.tf_dispatch_progress not in ("delivery", "return", "completed")
            plan.tf_eta_overdue = bool(active and plan.tf_eta and plan.tf_eta < today)
            plan.tf_lfd_overdue = bool(active and plan.tf_lfd and plan.tf_lfd < today)

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

    def _tf_display_name(self):
        self.ensure_one()
        if self.tf_is_container_product:
            return self.tf_container_number or self.serial_name or str(self.id)
        return self.serial_name or str(self.id)

    def name_get(self):
        result = []
        for record in self:
            label = record._tf_display_name()
            result.append((record.id, label))
        return result

    @api.depends("serial_name", "tf_container_number", "tf_is_container_product")
    def _compute_display_name(self):
        for record in self:
            record.display_name = record._tf_display_name()

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for vals in vals_list:
            vals = normalize_tf_container_selection_values(dict(vals))
            if vals.get("tf_address_partner_id") and not vals.get("tf_address_note"):
                vals["tf_address_note"] = format_tf_partner_address(
                    self.env["res.partner"].browse(vals["tf_address_partner_id"])
                )
            order_line = self.env["sale.order.line"].browse(vals.get("order_line_id")).exists()
            product_template = order_line.product_id.product_tmpl_id if order_line else self.env["product.template"]
            if product_template:
                if product_template.tf_is_container:
                    if not vals.get("tf_container_status"):
                        vals["tf_container_status"] = "on_water"
                    if not vals.get("tf_weight_unit"):
                        vals["tf_weight_unit"] = "kg"
                elif not product_template.tf_direct_container_to_client and not product_template.tf_cfs_pieces_flow:
                    if not vals.get("tf_dimension_unit"):
                        vals["tf_dimension_unit"] = "cm"
                    if not vals.get("tf_weight_unit"):
                        vals["tf_weight_unit"] = "kg"
            prepared_vals.append(vals)
        vals_list = prepared_vals
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
            "for_approval": {"hold", "hold_ssl", "hold_cbsa", "pickup", "tracking", "planning"},
            "hold": {"for_approval", "hold_ssl", "hold_cbsa", "pickup", "tracking", "planning", "dispatch"},
            "hold_ssl": {"for_approval", "hold", "hold_cbsa", "pickup", "tracking", "planning"},
            "hold_cbsa": {"for_approval", "hold", "hold_ssl", "pickup", "tracking", "planning"},
            "pickup": {"for_approval", "hold", "hold_ssl", "hold_cbsa", "tracking", "planning", "dispatch"},
            "tracking": {"for_approval", "hold", "hold_ssl", "hold_cbsa", "pickup", "planning", "dispatch"},
            "planning": {"for_approval", "hold", "hold_ssl", "hold_cbsa", "tracking", "dispatch"},
            "dispatch": {"for_approval", "hold", "hold_ssl", "hold_cbsa", "tracking"},
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
        vals = normalize_tf_container_selection_values(dict(vals))
        if vals.get("tf_address_partner_id") and "tf_address_note" not in vals:
            vals["tf_address_note"] = format_tf_partner_address(
                self.env["res.partner"].browse(vals["tf_address_partner_id"])
            )
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
            if record.order_id._tf_has_direct_container_to_client_flow():
                record._tf_ensure_direct_container_client_flow()
                continue
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
