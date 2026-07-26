# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    tf_transporter = fields.Char(string="Transporter/Carrier")
    tf_pod = fields.Boolean(string="POD")

    # Compatibility: some customized stock.picking form views (often Studio / migrated)
    # expect this field in modifiers, e.g. `readonly="not is_date_editable"` on
    # `scheduled_date`. Odoo 19 core doesn't define it, so we provide it.
    is_date_editable = fields.Boolean(compute="_compute_is_date_editable", store=False)

    @api.depends("state")
    def _compute_is_date_editable(self):
        for picking in self:
            picking.is_date_editable = picking.state not in ("done", "cancel")

    # -----------------------
    # Compat helpers (Odoo 19 safe)
    # -----------------------
    def _tf_moves(self):
        """Return picking moves across versions."""
        self.ensure_one()
        if "move_ids_without_package" in self._fields:
            return self.move_ids_without_package
        return self.move_ids

    def _tf_find_sale_line_for_move(self, picking, move):
        """Best-effort: sale_line_id if present, else map via picking.origin (SO name) + product."""
        if move.sale_line_id:
            return move.sale_line_id

        if not picking.origin:
            return self.env["sale.order.line"]

        so = self.env["sale.order"].search([("name", "=", picking.origin)], limit=1)
        if not so:
            return self.env["sale.order.line"]

        candidates = so.order_line.filtered(lambda l: l.product_id.id == move.product_id.id)
        if len(candidates) == 1:
            return candidates

        # If same product appears multiple times, try match by qty
        candidates2 = candidates.filtered(lambda l: int(l.product_uom_qty) == int(move.product_uom_qty or l.product_uom_qty))
        if len(candidates2) == 1:
            return candidates2

        return self.env["sale.order.line"]

    # -----------------------
    # Incoming: prefill move lines with planned serials + attributes
    # -----------------------
    def _tf_prefill_incoming_from_sale_serial_plan(self):
        for picking in self:
            if picking.picking_type_code != "incoming":
                continue

            for move in picking._tf_moves():
                if move.product_id.tracking != "serial":
                    continue

                sale_line = picking._tf_find_sale_line_for_move(picking, move)
                if not sale_line:
                    continue

                plan_lines = sale_line.tf_serial_plan_ids.sorted(lambda p: (p.sequence, p.id))
                if not plan_lines:
                    continue

                # If user already entered serials, don't override
                if move.move_line_ids.filtered(lambda ml: ml.lot_id or ml.lot_name):
                    continue

                blank_lines = move.move_line_ids.filtered(lambda ml: not ml.lot_id and not ml.lot_name)
                used_blank_lines = self.env["stock.move.line"]

                # Fill existing blank lines first (Odoo may pre-create them)
                idx = 0
                for ml in blank_lines:
                    if idx >= len(plan_lines):
                        break
                    plan = plan_lines[idx]
                    ml.write({
                        "lot_name": plan.serial_name,
                        "quantity": 1.0,
                        "tf_sale_serial_plan_id": plan.id,
                        "tf_description": plan.tf_description,
                        "tf_length": plan.tf_length,
                        "tf_width": plan.tf_width,
                        "tf_height": plan.tf_height,
                        "tf_dimension_unit": plan.tf_dimension_unit,
                        "tf_weight": plan.tf_weight,
                        "tf_weight_unit": plan.tf_weight_unit,
                        "tf_storage_rate": plan.tf_storage_rate,
                        "tf_location_note": plan.tf_location_note,
                    })
                    used_blank_lines |= ml
                    idx += 1

                # Create the remaining lines
                for plan in plan_lines[idx:]:
                    self.env["stock.move.line"].create({
                        "move_id": move.id,
                        "picking_id": picking.id,
                        "company_id": picking.company_id.id,
                        "product_id": move.product_id.id,
                        "product_uom_id": move.product_uom.id,
                        "location_id": move.location_id.id,
                        "location_dest_id": move.location_dest_id.id,
                        "quantity": 1.0,
                        "lot_name": plan.serial_name,
                        "tf_sale_serial_plan_id": plan.id,
                        "tf_description": plan.tf_description,
                        "tf_length": plan.tf_length,
                        "tf_width": plan.tf_width,
                        "tf_height": plan.tf_height,
                        "tf_dimension_unit": plan.tf_dimension_unit,
                        "tf_weight": plan.tf_weight,
                        "tf_weight_unit": plan.tf_weight_unit,
                        "tf_storage_rate": plan.tf_storage_rate,
                        "tf_location_note": plan.tf_location_note,
                    })

                # Remove technical placeholder rows (no serial + no attributes),
                # otherwise receipts can show a phantom extra line/quantity.
                (blank_lines - used_blank_lines).filtered(
                    lambda ml: not ml.picked
                    and not ml.lot_id
                    and not ml.lot_name
                    and not ml.tf_sale_serial_plan_id
                    and not ml.quant_id
                    and not ml.package_id
                    and not ml.result_package_id
                    and not ml.owner_id
                    and not ml.tf_description
                    and not ml.tf_length
                    and not ml.tf_width
                    and not ml.tf_height
                    and not ml.tf_dimension_unit
                    and not ml.tf_weight
                    and not ml.tf_weight_unit
                    and not ml.tf_storage_rate
                    and not ml.tf_location_note
                ).unlink()

    # -----------------------
    # Internal: prefill move lines with real lot_id (after receipt creates lots)
    # -----------------------
    def _tf_prefill_internal_from_sale_serial_plan_lots(self):
        for picking in self:
            if picking.picking_type_code != "internal":
                continue

            for move in picking._tf_moves():
                if move.product_id.tracking != "serial":
                    continue

                sale_line = picking._tf_find_sale_line_for_move(picking, move)
                if not sale_line:
                    continue

                plan_lines = sale_line.tf_serial_plan_ids.filtered(lambda p: p.lot_id).sorted(lambda p: (p.sequence, p.id))
                if not plan_lines:
                    continue

                if move.move_line_ids.filtered(lambda ml: ml.lot_id):
                    continue

                blank_lines = move.move_line_ids.filtered(lambda ml: not ml.lot_id)
                used_blank_lines = self.env["stock.move.line"]

                idx = 0
                for ml in blank_lines:
                    if idx >= len(plan_lines):
                        break
                    lot = plan_lines[idx].lot_id
                    ml.write({
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
                    })
                    used_blank_lines |= ml
                    idx += 1

                for plan in plan_lines[idx:]:
                    lot = plan.lot_id
                    self.env["stock.move.line"].create({
                        "move_id": move.id,
                        "picking_id": picking.id,
                        "company_id": picking.company_id.id,
                        "product_id": move.product_id.id,
                        "product_uom_id": move.product_uom.id,
                        "location_id": move.location_id.id,
                        "location_dest_id": move.location_dest_id.id,
                        "quantity": 1.0,
                        "lot_id": lot.id,
                        "tf_description": lot.tf_description,
                        "tf_length": lot.tf_length,
                        "tf_width": lot.tf_width,
                        "tf_height": lot.tf_height,
                        "tf_dimension_unit": lot.tf_dimension_unit,
                        "tf_weight": lot.tf_weight,
                        "tf_weight_unit": lot.tf_weight_unit,
                        "tf_storage_rate": lot.tf_storage_rate,
                        "tf_location_note": lot.tf_location_note,
                    })

                # Keep internal transfers aligned: drop empty technical placeholders.
                (blank_lines - used_blank_lines).filtered(
                    lambda ml: not ml.picked
                    and not ml.lot_id
                    and not ml.lot_name
                    and not ml.quant_id
                    and not ml.package_id
                    and not ml.result_package_id
                    and not ml.owner_id
                    and not ml.tf_description
                    and not ml.tf_length
                    and not ml.tf_width
                    and not ml.tf_height
                    and not ml.tf_dimension_unit
                    and not ml.tf_weight
                    and not ml.tf_weight_unit
                    and not ml.tf_storage_rate
                    and not ml.tf_location_note
                ).unlink()

    # -----------------------
    # Outgoing: auto-fill delivery from internal done (no re-entry)
    # -----------------------
    def _tf_autofill_outgoing_from_internal_done(self, internal_picking):
        self.ensure_one()
        if self.picking_type_code != "outgoing":
            return
        if self.location_id.id != internal_picking.location_dest_id.id:
            return

        for move in self._tf_moves():
            if move.product_id.tracking != "serial":
                continue
            if move.move_line_ids.filtered(lambda ml: ml.lot_id):
                continue

            internal_lines = internal_picking.move_line_ids.filtered(
                lambda ml: ml.product_id.id == move.product_id.id and ml.lot_id
            )
            if move.sale_line_id:
                internal_lines = internal_lines.filtered(
                    lambda ml: ml.move_id and ml.move_id.sale_line_id == move.sale_line_id
                )

            for il in internal_lines:
                lot = il.lot_id
                self.env["stock.move.line"].create({
                    "move_id": move.id,
                    "picking_id": self.id,
                    "company_id": self.company_id.id,
                    "product_id": move.product_id.id,
                    "product_uom_id": move.product_uom.id,
                    "location_id": move.location_id.id,
                    "location_dest_id": move.location_dest_id.id,
                    "quantity": 1.0,
                    "lot_id": lot.id,
                    "tf_description": lot.tf_description,
                    "tf_length": lot.tf_length,
                    "tf_width": lot.tf_width,
                    "tf_height": lot.tf_height,
                    "tf_dimension_unit": lot.tf_dimension_unit,
                    "tf_weight": lot.tf_weight,
                    "tf_weight_unit": lot.tf_weight_unit,
                    "tf_storage_rate": lot.tf_storage_rate,
                    "tf_location_note": lot.tf_location_note,
                })

    # -----------------------
    # Hooks: copy to lot + prefill next steps
    # -----------------------
    def _action_done(self):
        res = super()._action_done()

        for picking in self:
            # Incoming done -> copy final values to lot + stamp reception date
            if picking.picking_type_code == "incoming":
                done_date = picking.date_done.date() if picking.date_done else fields.Date.context_today(picking)

                for ml in picking.move_line_ids:
                    if ml.product_id.tracking != "serial" or not ml.lot_id:
                        continue
                    lot = ml.lot_id
                    lot.write({
                        "tf_description": ml.tf_description,
                        "tf_length": ml.tf_length,
                        "tf_width": ml.tf_width,
                        "tf_height": ml.tf_height,
                        "tf_dimension_unit": ml.tf_dimension_unit,
                        "tf_weight": ml.tf_weight,
                        "tf_weight_unit": ml.tf_weight_unit,
                        "tf_storage_rate": ml.tf_storage_rate,
                        "tf_location_note": ml.tf_location_note,
                        "tf_reception_date": lot.tf_reception_date or done_date,
                    })

                    if ml.tf_sale_serial_plan_id:
                        ml.tf_sale_serial_plan_id.write({
                            "serial_name": lot.name,
                            "tf_description": ml.tf_description,
                            "tf_length": ml.tf_length,
                            "tf_width": ml.tf_width,
                            "tf_height": ml.tf_height,
                            "tf_dimension_unit": ml.tf_dimension_unit,
                            "tf_weight": ml.tf_weight,
                            "tf_weight_unit": ml.tf_weight_unit,
                            "tf_storage_rate": ml.tf_storage_rate,
                            "tf_location_note": ml.tf_location_note,
                            "lot_id": lot.id,
                        })

                # Prefill internal transfers for same origin (SO name)
                if picking.origin:
                    internal_pickings = self.env["stock.picking"].search([
                        ("picking_type_code", "=", "internal"),
                        ("state", "not in", ("done", "cancel")),
                        ("origin", "=", picking.origin),
                    ])
                    internal_pickings._tf_prefill_internal_from_sale_serial_plan_lots()

            # Outgoing done -> stamp delivery date
            if picking.picking_type_code == "outgoing":
                done_date = picking.date_done.date() if picking.date_done else fields.Date.context_today(picking)
                for ml in picking.move_line_ids:
                    if ml.product_id.tracking == "serial" and ml.lot_id:
                        ml.lot_id.write({"tf_delivery_date": ml.lot_id.tf_delivery_date or done_date})

            # Internal done -> auto-fill outgoing delivery (Transport -> Customer)
            if picking.picking_type_code == "internal" and picking.origin:
                outgoing_pickings = self.env["stock.picking"].search([
                    ("picking_type_code", "=", "outgoing"),
                    ("state", "in", ("confirmed", "assigned", "waiting")),
                    ("origin", "=", picking.origin),
                    ("location_id", "=", picking.location_dest_id.id),
                ])
                for op in outgoing_pickings:
                    op._tf_autofill_outgoing_from_internal_done(picking)

        return res
