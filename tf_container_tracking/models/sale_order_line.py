# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    tf_container_line_id = fields.Many2one(
        "sale.order.line",
        string="Container Line",
        copy=False,
        index=True,
        ondelete="set null",
        domain="[('order_id', '=', order_id)]",
        help="Container sales line that this piece line belongs to.",
    )
    tf_piece_line_ids = fields.One2many(
        "sale.order.line",
        "tf_container_line_id",
        string="Linked Piece Lines",
        copy=False,
    )
    tf_auto_piece_line = fields.Boolean(
        string="Auto Piece Line",
        copy=False,
        help="Technical flag for the generic Piece line automatically created below a container line.",
    )

    def _tf_is_container_line(self):
        self.ensure_one()
        return bool(self.product_id and self.product_id.product_tmpl_id.tf_is_container)

    def _tf_requires_container_assignment(self):
        self.ensure_one()
        return bool(self.product_id and self.product_id.product_tmpl_id.tf_requires_container)

    def _tf_is_custom_logistics_line(self):
        self.ensure_one()
        product = self.product_id.product_tmpl_id
        return bool(
            product.tf_is_container
            or product.tf_requires_container
            or product.tf_direct_container_to_client
            or product.tf_cfs_pieces_flow
        )

    def _tf_is_container_or_piece_line(self):
        self.ensure_one()
        product = self.product_id.product_tmpl_id
        return bool(product.tf_is_container or product.tf_requires_container)

    @api.constrains("tf_container_line_id", "order_id", "product_id")
    def _check_tf_container_line_id(self):
        for line in self:
            container_line = line.tf_container_line_id
            if not container_line:
                continue
            if container_line == line:
                raise ValidationError(_("A piece line cannot be linked to itself as a container line."))
            if container_line.order_id != line.order_id:
                raise ValidationError(_("The linked container line must belong to the same Sales Order."))
            if not container_line.product_id.product_tmpl_id.tf_is_container:
                raise ValidationError(_("The linked container line must use a container product."))
            if line.product_id.product_tmpl_id.tf_is_container:
                raise ValidationError(_("A container product line cannot be linked under another container line."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get("tf_skip_line_sequence_normalize"):
            vals_list = self._tf_prepare_missing_line_sequences(vals_list)
        lines = super().create(vals_list)
        if not self.env.context.get("tf_skip_container_piece_line_sync"):
            lines._tf_sync_container_piece_lines_after_create()
        if not self.env.context.get("tf_skip_line_sequence_normalize"):
            lines._tf_normalize_container_piece_line_sequences()
            lines.mapped("order_id").invalidate_recordset(["order_line"])
        return lines

    def write(self, vals):
        res = super().write(vals)
        if (
            not self.env.context.get("tf_skip_container_piece_line_sync")
            and {"product_id", "order_id", "sequence"} & set(vals)
        ):
            self._tf_sync_container_piece_lines_after_create()
        if (
            not self.env.context.get("tf_skip_line_sequence_normalize")
            and {"product_id", "order_id", "sequence", "display_type"} & set(vals)
        ):
            self._tf_normalize_container_piece_line_sequences()
            self.mapped("order_id").invalidate_recordset(["order_line"])
        return res

    @api.model
    def _tf_prepare_missing_line_sequences(self, vals_list):
        prepared_vals = []
        next_sequence_by_order = {}
        for original_vals in vals_list:
            vals = dict(original_vals)
            if "sequence" not in vals and vals.get("order_id"):
                order_id = vals["order_id"]
                next_sequence = next_sequence_by_order.get(order_id)
                if next_sequence is None:
                    order = self.env["sale.order"].browse(order_id)
                    next_sequence = max(order.order_line.mapped("sequence") or [0])
                next_sequence += 10
                vals["sequence"] = next_sequence
                next_sequence_by_order[order_id] = next_sequence
            prepared_vals.append(vals)
        return prepared_vals

    def _tf_ordered_product_lines(self):
        self.ensure_one()
        return self.order_id.order_line.filtered(lambda line: not line.display_type).sorted(
            lambda line: (line.sequence, line.id)
        )

    def _tf_previous_container_line(self):
        self.ensure_one()
        current_key = (self.sequence, self.id)
        previous = self.env["sale.order.line"]
        for line in self._tf_ordered_product_lines():
            line_key = (line.sequence, line.id)
            if line_key >= current_key:
                break
            if line._tf_is_container_line():
                previous = line
        return previous

    def _tf_container_lines_for_assignment(self):
        self.ensure_one()
        if self._tf_is_container_line():
            return self
        if not self._tf_requires_container_assignment():
            return self.env["sale.order.line"]
        if self.tf_container_line_id:
            return self.tf_container_line_id
        previous_container = self._tf_previous_container_line()
        if previous_container:
            return previous_container
        return self.order_id.order_line.filtered(lambda line: line._tf_is_container_line()).sorted(
            lambda line: (line.sequence, line.id)
        )

    def _tf_container_plans_for_assignment(self):
        self.ensure_one()
        return self._tf_container_lines_for_assignment().mapped("tf_serial_plan_ids").filtered(
            "tf_is_container_product"
        ).sorted(lambda plan: (plan.order_line_id.sequence, plan.order_line_id.id, plan.sequence, plan.id))

    def _tf_container_serial_index_start(self):
        self.ensure_one()
        if not self._tf_is_container_line():
            return 1
        start = 1
        current_key = (self.sequence, self.id)
        for line in self.order_id.order_line.filtered(lambda item: item._tf_is_container_line()).sorted(
            lambda item: (item.sequence, item.id)
        ):
            if (line.sequence, line.id) >= current_key:
                break
            start += int(line.product_uom_qty or len(line.tf_serial_plan_ids) or 0)
        return start

    def _tf_container_serial_seed(self, local_index):
        self.ensure_one()
        order_name = (self.order_id.name or "SO").replace("/", "-").replace(" ", "")
        global_index = self._tf_container_serial_index_start() + int(local_index or 1) - 1
        return f"{order_name}-C{global_index:02d}"

    def _tf_default_container_type(self):
        self.ensure_one()
        if not self._tf_is_container_line():
            return False
        product_template = self.product_id.product_tmpl_id
        return product_template.tf_container_type or self.product_id.display_name or product_template.display_name

    @api.model
    def _tf_find_default_piece_product(self):
        Product = self.env["product.product"]
        base_domain = [
            ("active", "=", True),
            ("sale_ok", "=", True),
            ("product_tmpl_id.tf_requires_container", "=", True),
        ]
        for name in ("Piece", "Pieces"):
            product = Product.search(base_domain + [("name", "=", name)], limit=1)
            if product:
                return product
        return Product.browse()

    def _tf_sync_container_piece_lines_after_create(self):
        orders = self.mapped("order_id")
        orders.invalidate_recordset(["order_line"])
        for order in orders:
            current_container = self.env["sale.order.line"]
            for line in order.order_line.filtered(lambda item: not item.display_type).sorted(lambda item: (item.sequence, item.id)):
                if line._tf_is_container_line():
                    current_container = line
                    continue
                if line._tf_requires_container_assignment() and not line.tf_container_line_id and current_container:
                    line.with_context(tf_skip_container_piece_line_sync=True).tf_container_line_id = current_container.id

        piece_product = self._tf_find_default_piece_product()
        if not piece_product:
            return

        container_lines = self.filtered(lambda line: line._tf_is_container_line())
        for container_line in container_lines:
            container_line.invalidate_recordset(["tf_piece_line_ids"])
            if container_line.tf_piece_line_ids:
                continue
            self.with_context(
                tf_skip_container_piece_line_sync=True,
                tf_skip_line_sequence_normalize=True,
            ).create({
                "order_id": container_line.order_id.id,
                "product_id": piece_product.id,
                "product_uom_qty": container_line.product_uom_qty,
                "product_uom_id": piece_product.uom_id.id,
                "price_unit": 0.0,
                "sequence": container_line.sequence + 1,
                "tf_container_line_id": container_line.id,
                "tf_auto_piece_line": True,
            })

    def _tf_normalize_container_piece_line_sequences(self):
        orders = self.mapped("order_id")
        orders.invalidate_recordset(["order_line"])
        for order in orders:
            ordered_lines = order.order_line.sorted(lambda line: (line.sequence, line.id))
            container_piece_lines = self.env["sale.order.line"]
            for container_line in ordered_lines.filtered(lambda line: not line.display_type and line._tf_is_container_line()):
                container_piece_lines |= container_line
                container_piece_lines |= container_line.tf_piece_line_ids.sorted(
                    lambda line: (line.tf_auto_piece_line, line.sequence, line.id)
                )
            container_piece_lines |= ordered_lines.filtered(
                lambda line: not line.display_type
                and line._tf_requires_container_assignment()
                and not line.tf_container_line_id
            )
            other_lines = ordered_lines - container_piece_lines
            target_lines = container_piece_lines + other_lines
            for index, line in enumerate(target_lines, start=1):
                target_sequence = index * 10
                if line.sequence == target_sequence:
                    continue
                line.with_context(
                    tf_skip_container_piece_line_sync=True,
                    tf_skip_line_sequence_normalize=True,
                ).sequence = target_sequence
            order.invalidate_recordset(["order_line"])
        return True

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        custom_lines = self.filtered(lambda line: line._tf_is_custom_logistics_line())
        regular_lines = self - custom_lines
        if not regular_lines:
            return True
        return super(SaleOrderLine, regular_lines)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty
        )

    def action_open_tf_serial_wizard(self):
        action = super().action_open_tf_serial_wizard()
        self.ensure_one()
        action["context"] = dict(action.get("context", {}), dialog_size="extra-large")
        if self.product_id.product_tmpl_id.tf_is_container:
            container_view = self.env.ref("tf_container_tracking.view_tf_sale_serial_wizard_form_container")
            action["view_id"] = container_view.id
            action["views"] = [(container_view.id, "form")]
        else:
            base_view = self.env.ref("tf_serial_quote_attributes.view_tf_sale_serial_wizard_form")
            action["view_id"] = base_view.id
            action["views"] = [(base_view.id, "form")]
        return action
