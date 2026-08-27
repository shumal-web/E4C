# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class TfSaleSerialWizard(models.TransientModel):
    _inherit = "tf.sale.serial.wizard"

    qty = fields.Float(
        related="order_line_id.product_uom_qty",
        readonly=False,
    )
    tf_is_container_product = fields.Boolean(
        related="product_id.product_tmpl_id.tf_is_container",
        readonly=True,
    )
    tf_requires_container = fields.Boolean(
        related="product_id.product_tmpl_id.tf_requires_container",
        readonly=True,
    )
    tf_has_container_plans = fields.Boolean(
        compute="_compute_tf_has_container_plans",
        readonly=True,
    )
    tf_show_assign_workflow = fields.Boolean(
        compute="_compute_tf_show_assign_workflow",
        readonly=True,
    )
    assign_line_ids = fields.One2many(
        "tf.sale.serial.wizard.assign.line",
        "wizard_id",
        string="Container Distribution",
    )
    tf_assign_length = fields.Float(string="Length")
    tf_assign_width = fields.Float(string="Width")
    tf_assign_height = fields.Float(string="Height")
    tf_assign_dimension_unit = fields.Selection(
        [("mm", "mm"), ("cm", "cm"), ("m", "m"), ("in", "in"), ("ft", "ft")],
        string="Dim Unit",
    )
    tf_assign_weight = fields.Float(string="Weight")
    tf_assign_weight_unit = fields.Selection(
        [("g", "g"), ("kg", "kg"), ("lb", "lb")],
        string="Weight Unit",
    )

    def _tf_cm_to_inches(self, value):
        return round((value or 0.0) / 2.54, 2)

    def action_tf_convert_cm_to_inches(self):
        self.ensure_one()
        converted = False

        if self.tf_assign_dimension_unit == "cm":
            self.write({
                "tf_assign_length": self._tf_cm_to_inches(self.tf_assign_length),
                "tf_assign_width": self._tf_cm_to_inches(self.tf_assign_width),
                "tf_assign_height": self._tf_cm_to_inches(self.tf_assign_height),
                "tf_assign_dimension_unit": "in",
            })
            converted = True

        for line in self.line_ids.filtered(lambda item: item.tf_dimension_unit == "cm"):
            line.write({
                "tf_length": self._tf_cm_to_inches(line.tf_length),
                "tf_width": self._tf_cm_to_inches(line.tf_width),
                "tf_height": self._tf_cm_to_inches(line.tf_height),
                "tf_dimension_unit": "in",
            })
            converted = True

        if not converted:
            raise UserError(_("No dimensions with Dim Unit = cm were found to convert."))

        return {
            "type": "ir.actions.act_window",
            "res_model": "tf.sale.serial.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    @api.depends("order_line_id.order_id.order_line.tf_serial_plan_ids.tf_is_container_product")
    def _compute_tf_has_container_plans(self):
        for wizard in self:
            order = wizard.order_line_id.order_id
            container_plans = order.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product") if order else self.env["tf.sale.serial.plan"]
            wizard.tf_has_container_plans = bool(container_plans)

    @api.depends("tf_is_container_product", "tf_requires_container", "tf_has_container_plans")
    def _compute_tf_show_assign_workflow(self):
        for wizard in self:
            wizard.tf_show_assign_workflow = bool(
                not wizard.tf_is_container_product
                and wizard.tf_requires_container
                and wizard.tf_has_container_plans
            )

    def _tf_container_seed(self, index, order_name=None):
        if order_name is None:
            order_name = self.order_id.name if self else "SO"
        order_name = (order_name or "SO").replace("/", "-").replace(" ", "")
        return f"{order_name}-C{index:02d}"

    def _tf_case_serial_seed(self, container_index, case_index, total_cases):
        self.ensure_one()
        order_name = (self.order_id.name or "SO").replace("/", "-").replace(" ", "")
        return f"{order_name}-{container_index} {case_index} of {total_cases}"

    def _tf_sync_assign_lines_from_order(self):
        self.ensure_one()
        if self.tf_is_container_product or not self.tf_requires_container:
            return self.env["tf.sale.serial.wizard.assign.line"]

        container_plans = self.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
        container_plans = container_plans.sorted(lambda p: (p.sequence, p.id))
        if not container_plans:
            self.assign_line_ids = [(5, 0, 0)]
            return self.assign_line_ids

        existing_lines = self.assign_line_ids.sorted(lambda l: (l.sequence, l.id))
        existing_by_container = {
            line.container_plan_id.id: line
            for line in existing_lines.filtered("container_plan_id")
        }
        existing_by_sequence = {
            line.sequence: line
            for line in existing_lines
            if line.sequence
        }
        piece_counts = {}
        for plan in self.order_line_id.tf_serial_plan_ids.filtered(lambda p: p.tf_container_plan_id):
            piece_counts.setdefault(plan.tf_container_plan_id.id, 0)
            piece_counts[plan.tf_container_plan_id.id] += 1

        commands = [(5, 0, 0)]
        for index, container_plan in enumerate(container_plans, start=1):
            expected_sequence = index * 10
            existing_line = (
                existing_by_container.get(container_plan.id)
                or existing_by_sequence.get(expected_sequence)
                or (existing_lines[index - 1] if len(existing_lines) >= index else False)
            )
            case_qty = existing_line.case_qty if existing_line else piece_counts.get(container_plan.id, 0)
            commands.append((0, 0, {
                "sequence": expected_sequence,
                "container_plan_id": container_plan.id,
                "case_qty": case_qty,
            }))

        self.write({"assign_line_ids": commands})
        return self.assign_line_ids.sorted(lambda l: ((l.container_plan_id.sequence or 0), l.sequence, l.id))

    def _tf_get_assign_lines_for_action(self):
        self.ensure_one()
        if self.tf_is_container_product or not self.tf_requires_container:
            return self.env["tf.sale.serial.wizard.assign.line"]

        container_plans = self.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
        container_plans = container_plans.sorted(lambda p: (p.sequence, p.id))
        if not container_plans:
            return self.env["tf.sale.serial.wizard.assign.line"]

        if not self.assign_line_ids:
            return self._tf_sync_assign_lines_from_order()

        assign_lines = self.assign_line_ids.sorted(lambda l: (l.sequence, l.id))
        lines_by_sequence = {line.sequence: line for line in assign_lines}
        missing_commands = []
        for index, container_plan in enumerate(container_plans, start=1):
            sequence = index * 10
            line = lines_by_sequence.get(sequence)
            if not line:
                missing_commands.append((0, 0, {
                    "sequence": sequence,
                    "container_plan_id": container_plan.id,
                    "case_qty": 0,
                }))
                continue
            updates = {}
            if not line.container_plan_id:
                updates["container_plan_id"] = container_plan.id
            if line.sequence != sequence:
                updates["sequence"] = sequence
            if updates:
                line.write(updates)
        if missing_commands:
            self.write({"assign_line_ids": missing_commands})
        return self.assign_line_ids.sorted(lambda l: ((l.container_plan_id.sequence or 0), l.sequence, l.id))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order_line_id = self.env.context.get("default_order_line_id")
        if not order_line_id:
            return res

        sol = self.env["sale.order.line"].browse(order_line_id)
        if not sol.exists():
            return res

        existing_plans = sol.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        is_container = bool(sol.product_id.product_tmpl_id.tf_is_container)
        allow_blank_serial = bool(
            not is_container
            and sol.product_id.product_tmpl_id.tf_requires_container
        )
        line_commands = res.get("line_ids") or []
        if not line_commands and is_container and sol.product_id.tracking == "serial":
            target = int(sol.product_uom_qty or 0)
            for index in range(1, target + 1):
                seeded_name = self._tf_container_seed(index, order_name=sol.order_id.name)
                line_commands.append((0, 0, {
                    "sequence": index * 10,
                    "serial_name": seeded_name,
                    "tf_container_number": seeded_name,
                    "tf_internal_status": "for_approval",
                }))
        if not line_commands:
            return res

        existing_count = len(existing_plans)
        sequence_map = {plan.sequence: plan for plan in existing_plans}
        serial_map = {plan.serial_name: plan for plan in existing_plans if plan.serial_name}
        assign_commands = []
        if allow_blank_serial:
            container_plans = sol.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
            container_plans = container_plans.sorted(lambda p: (p.sequence, p.id))
            piece_counts = {}
            for plan in existing_plans.filtered(lambda p: p.tf_container_plan_id):
                piece_counts.setdefault(plan.tf_container_plan_id.id, 0)
                piece_counts[plan.tf_container_plan_id.id] += 1
            for container_plan in container_plans:
                assign_commands.append((0, 0, {
                    "sequence": len(assign_commands) * 10 + 10,
                    "container_plan_id": container_plan.id,
                    "case_qty": piece_counts.get(container_plan.id, 0),
                }))
            if existing_plans:
                sample_plan = existing_plans[:1]
                res.update({
                    "tf_assign_length": sample_plan.tf_length,
                    "tf_assign_width": sample_plan.tf_width,
                    "tf_assign_height": sample_plan.tf_height,
                    "tf_assign_dimension_unit": sample_plan.tf_dimension_unit,
                    "tf_assign_weight": sample_plan.tf_weight,
                    "tf_assign_weight_unit": sample_plan.tf_weight_unit,
                })

        patched_commands = []
        for index, command in enumerate(line_commands, start=1):
            if not isinstance(command, (list, tuple)) or len(command) != 3 or command[0] != 0:
                patched_commands.append(command)
                continue
            vals = dict(command[2] or {})
            plan = serial_map.get(vals.get("serial_name")) or sequence_map.get(vals.get("sequence"))

            if is_container and index > existing_count:
                seeded_name = self._tf_container_seed(index, order_name=sol.order_id.name)
                vals["serial_name"] = seeded_name
                vals.setdefault("tf_container_number", seeded_name)
                vals.setdefault("tf_internal_status", "for_approval")
            elif allow_blank_serial and not plan:
                vals["serial_name"] = False

            vals.update({
                "plan_id": plan.id if plan else False,
                "tf_container_plan_id": plan.tf_container_plan_id.id if plan and plan.tf_container_plan_id else False,
                "tf_container_number": plan.tf_container_number if plan else vals.get("tf_container_number"),
                "tf_internal_status": plan.tf_internal_status if plan else vals.get("tf_internal_status"),
                "tf_port_to_destuff": plan.tf_port_to_destuff if plan else False,
                    "tf_container_status": plan.tf_container_status if plan else vals.get("tf_container_status"),
                    "tf_container_location": plan.tf_container_location if plan else False,
                    "tf_eta": plan.tf_eta if plan else False,
                    "tf_lfd": plan.tf_lfd if plan else False,
                    "tf_cutoff_date": plan.tf_cutoff_date if plan else False,
                    "tf_ssl": plan.tf_ssl if plan else False,
                    "tf_container_type": (
                        plan.tf_container_type
                        if plan
                        else (sol.product_id.product_tmpl_id.tf_container_type if is_container else False)
                    ),
                    "tf_chassis_no": plan.tf_chassis_no if plan else False,
                    "tf_pubk_no": plan.tf_pubk_no if plan else False,
                    "tf_import_export": plan.tf_import_export if plan else sol.order_id.tf_shipment_type,
                })
            patched_commands.append((0, 0, vals))

        res["line_ids"] = patched_commands
        if assign_commands:
            res["assign_line_ids"] = assign_commands
        return res

    def action_generate_serials(self):
        self.ensure_one()
        if not self.tf_is_container_product and self.tf_requires_container:
            target = int(self.qty or 0)
            existing = len(self.line_ids)
            if target <= 0:
                raise UserError(_("Quantity must be > 0 to prepare serial lines."))

            for index in range(existing + 1, target + 1):
                self.line_ids = [
                    (
                        0,
                        0,
                        {
                            "sequence": index * 10,
                            "serial_name": False,
                        },
                    )
                ]

            return {
                "type": "ir.actions.act_window",
                "res_model": "tf.sale.serial.wizard",
                "res_id": self.id,
                "view_mode": "form",
                "target": "new",
            }

        if not self.tf_is_container_product:
            return super().action_generate_serials()

        if self.product_id.tracking != "serial":
            raise UserError(_("This product is not tracked by unique serial number."))

        target = int(self.qty or 0)
        existing = len(self.line_ids)
        if target <= 0:
            raise UserError(_("Quantity must be > 0 to generate serials."))

        for index in range(existing + 1, target + 1):
            seeded_name = self._tf_container_seed(index, order_name=self.order_id.name)
            self.line_ids = [
                (
                    0,
                    0,
                    {
                        "sequence": index * 10,
                        "serial_name": seeded_name,
                        "tf_container_number": seeded_name,
                        "tf_internal_status": "for_approval",
                        "tf_container_type": self.product_id.product_tmpl_id.tf_container_type,
                        "tf_import_export": self.order_id.tf_shipment_type,
                    },
                )
            ]

        return {
            "type": "ir.actions.act_window",
            "res_model": "tf.sale.serial.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_auto_assign_containers(self):
        self.ensure_one()
        if self.tf_is_container_product:
            return False
        container_plans = self.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
        container_plans = container_plans.sorted(lambda p: (p.sequence, p.id))
        if not container_plans:
            raise UserError(_("No container serials found in this order."))
        grouped_lines = {}
        ordered_lines = self.line_ids.sorted(lambda l: (l.sequence, l.id))
        for index, line in enumerate(ordered_lines):
            container_plan = container_plans[index % len(container_plans)]
            line.tf_container_plan_id = container_plan
            grouped_lines.setdefault(container_plan.id, self.env["tf.sale.serial.wizard.line"])
            grouped_lines[container_plan.id] |= line

        for container_index, container_plan in enumerate(container_plans, start=1):
            container_lines = grouped_lines.get(container_plan.id, self.env["tf.sale.serial.wizard.line"]).sorted(
                lambda l: (l.sequence, l.id)
            )
            total_cases = len(container_lines)
            for case_index, line in enumerate(container_lines, start=1):
                line.serial_name = self._tf_case_serial_seed(container_index, case_index, total_cases)
        return {
            "type": "ir.actions.act_window",
            "res_model": "tf.sale.serial.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_assign(self):
        self.ensure_one()
        if not self.tf_show_assign_workflow:
            return self.action_generate_serials()

        container_lines = self._tf_get_assign_lines_for_action()
        if not container_lines:
            raise UserError(_("No container serials are available for assignment."))

        target = int(self.qty or 0)
        total_cases = sum(int(line.case_qty or 0) for line in container_lines)
        if total_cases != target:
            raise UserError(
                _("Total assigned case quantity must match the product quantity (%s). Current total: %s")
                % (target, total_cases)
            )

        existing_plans = self.order_line_id.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
        new_commands = []
        line_index = 0
        for container_index, assign_line in enumerate(container_lines, start=1):
            total_cases = int(assign_line.case_qty or 0)
            for case_index in range(1, total_cases + 1):
                plan = existing_plans[line_index] if line_index < len(existing_plans) else False
                vals = {
                    "sequence": (line_index + 1) * 10,
                    "serial_name": self._tf_case_serial_seed(container_index, case_index, total_cases),
                    "plan_id": plan.id if plan else False,
                    "tf_container_plan_id": assign_line.container_plan_id.id,
                    "tf_description": plan.tf_description if plan and plan.tf_description else False,
                    "tf_length": self.tf_assign_length,
                    "tf_width": self.tf_assign_width,
                    "tf_height": self.tf_assign_height,
                    "tf_dimension_unit": self.tf_assign_dimension_unit,
                    "tf_weight": self.tf_assign_weight,
                    "tf_weight_unit": self.tf_assign_weight_unit,
                    "tf_storage_rate": plan.tf_storage_rate if plan else False,
                    "tf_location_note": plan.tf_location_note if plan else False,
                }
                new_commands.append((0, 0, vals))
                line_index += 1

        self.write({"line_ids": [(5, 0, 0)] + new_commands})
        return {
            "type": "ir.actions.act_window",
            "res_model": "tf.sale.serial.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        if self.product_id.tracking != "serial":
            raise UserError(_("This product is not tracked by unique serial number."))

        target = int(self.qty or 0)
        wizard_lines = self.line_ids.sorted(lambda line: (line.sequence, line.id))
        if len(wizard_lines) != target:
            raise UserError(_("You must have exactly %s serial lines (same as quantity).") % target)

        container_plans_in_order = self.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
        requires_container = bool(
            not self.tf_is_container_product
            and self.tf_requires_container
            and container_plans_in_order
        )

        missing_container = []
        for line in wizard_lines:
            allow_blank_serial = bool(not self.tf_is_container_product and self.tf_requires_container)
            if not line.serial_name and not allow_blank_serial:
                raise UserError(_("Serial Number cannot be empty."))
            if line.tf_container_plan_id:
                if line.tf_container_plan_id.order_id != self.order_id:
                    raise UserError(_("Container serial must belong to the same sales order."))
                if not line.tf_container_plan_id.tf_is_container_product:
                    raise UserError(_("Selected container serial must come from a container product line."))
            if requires_container and not line.tf_container_plan_id:
                missing_container.append(str(line.sequence))

        if missing_container:
            raise UserError(
                _("Container assignment is required for this product. Missing at sequence(s): %s")
                % ", ".join(missing_container)
            )

        plan_model = self.env["tf.sale.serial.plan"]
        existing_plans = self.order_line_id.tf_serial_plan_ids
        kept_plans = plan_model.browse()
        existing_by_id = {plan.id: plan for plan in existing_plans}
        existing_by_sequence = {plan.sequence: plan for plan in existing_plans}
        existing_by_serial = {plan.serial_name: plan for plan in existing_plans if plan.serial_name}

        for line in wizard_lines:
            values = {
                "sequence": line.sequence,
                "serial_name": line.serial_name,
                "tf_description": line.tf_description,
                "tf_length": line.tf_length,
                "tf_width": line.tf_width,
                "tf_height": line.tf_height,
                "tf_dimension_unit": line.tf_dimension_unit,
                "tf_weight": line.tf_weight,
                "tf_weight_unit": line.tf_weight_unit,
                "tf_storage_rate": line.tf_storage_rate,
                "tf_location_note": line.tf_location_note,
                "tf_container_plan_id": False if self.tf_is_container_product else line.tf_container_plan_id.id,
                "tf_container_number": line.tf_container_number or (line.serial_name if self.tf_is_container_product else False),
                "tf_internal_status": line.tf_internal_status,
                "tf_port_to_destuff": line.tf_port_to_destuff,
                "tf_container_status": line.tf_container_status,
                "tf_container_location": line.tf_container_location,
                "tf_eta": line.tf_eta,
                "tf_lfd": line.tf_lfd,
                "tf_cutoff_date": line.tf_cutoff_date,
                "tf_ssl": line.tf_ssl,
                "tf_container_type": line.tf_container_type,
                "tf_chassis_no": line.tf_chassis_no,
                "tf_pubk_no": line.tf_pubk_no,
                "tf_import_export": line.tf_import_export,
            }

            existing_plan = False
            if line.plan_id and line.plan_id.id in existing_by_id:
                existing_plan = existing_by_id[line.plan_id.id]
            elif self.tf_is_container_product:
                existing_plan = existing_by_serial.get(line.serial_name) or existing_by_sequence.get(line.sequence)
            else:
                existing_plan = existing_by_sequence.get(line.sequence)
            if existing_plan:
                existing_plan.write(values)
                kept_plans |= existing_plan
            else:
                values.update({
                    "order_id": self.order_id.id,
                    "order_line_id": self.order_line_id.id,
                })
                created = plan_model.create(values)
                kept_plans |= created

        to_remove = existing_plans - kept_plans
        blocked = to_remove.filtered(lambda plan: plan.tf_piece_plan_ids)
        if blocked:
            names = ", ".join(blocked.mapped("serial_name"))
            raise UserError(
                _("Cannot delete container serial(s) linked to piece serials: %s. Reassign pieces first.") % names
            )
        to_remove.unlink()

        return {"type": "ir.actions.act_window_close"}


class TfSaleSerialWizardLine(models.TransientModel):
    _inherit = "tf.sale.serial.wizard.line"

    serial_name = fields.Char(string="Serial Number", required=False)

    plan_id = fields.Many2one("tf.sale.serial.plan", string="Source Plan", readonly=True)
    order_id = fields.Many2one(related="wizard_id.order_id", readonly=True)
    wizard_is_container_product = fields.Boolean(related="wizard_id.tf_is_container_product", readonly=True)

    tf_container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Number",
    )

    tf_container_number = fields.Char(string="Container #")
    tf_internal_status = fields.Selection(
        [
            ("for_approval", "For Approval"),
            ("hold_ssl", "Hold SSL"),
            ("hold_cbsa", "Hold CBSA"),
            ("tracking", "Tracking"),
            ("planning", "Planning"),
            ("dispatch", "Dispatch"),
        ],
        string="Internal Status",
        default="for_approval",
    )
    tf_port_to_destuff = fields.Char(string="Origin")
    tf_container_status = fields.Selection(
        [
            ("on_water", "On the Water"),
            ("at_port", "At Port"),
            ("ready", "Ready"),
            ("ready_for_return", "Ready for Return"),
            ("picked_up", "Picked Up"),
            ("de_stuffed", "De Stuffed"),
            ("returned", "Returned"),
        ],
        string="Container Status",
        default="on_water",
    )
    tf_container_location = fields.Char(string="Container Location")
    tf_eta = fields.Date(string="ETA")
    tf_lfd = fields.Date(string="LFD")
    tf_cutoff_date = fields.Date(string="Cutoff")
    tf_ssl = fields.Char(string="SSL")
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


class TfSaleSerialWizardAssignLine(models.TransientModel):
    _name = "tf.sale.serial.wizard.assign.line"
    _description = "TF Sale Serial Wizard Assign Line"
    _order = "sequence, id"

    wizard_id = fields.Many2one("tf.sale.serial.wizard", required=True, ondelete="cascade")
    sequence = fields.Integer(default=10)
    container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container Number",
        domain="[('order_id', '=', wizard_id.order_id), ('tf_is_container_product', '=', True)]",
    )
    case_qty = fields.Integer(string="# of Case", default=0)

    @api.model_create_multi
    def create(self, vals_list):
        filtered_vals = []
        for vals in vals_list:
            if vals.get("wizard_id") and not vals.get("container_plan_id"):
                wizard = self.env["tf.sale.serial.wizard"].browse(vals["wizard_id"])
                container_plans = wizard.order_id.order_line.mapped("tf_serial_plan_ids").filtered("tf_is_container_product")
                container_plans = container_plans.sorted(lambda p: (p.sequence, p.id))
                sequence = vals.get("sequence") or 10
                index = max(int(sequence / 10) - 1, 0)
                if len(container_plans) > index:
                    vals["container_plan_id"] = container_plans[index].id
            if vals.get("container_plan_id") or vals.get("case_qty"):
                filtered_vals.append(vals)
        if not filtered_vals:
            return self.browse()
        return super().create(filtered_vals)
