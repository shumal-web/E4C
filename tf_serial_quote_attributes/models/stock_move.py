# -*- coding: utf-8 -*-
from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def action_show_details(self):
        """Prefill from quotation serial plan before opening Detailed Operations.

        IMPORTANT (Odoo 19): do NOT force a different res_model/view_id here.
        Doing so can break the OWL view parsing if the action returned by super()
        targets a different model (e.g. stock.move).

        Instead, we:
        - prefill missing move lines
        - set a context flag so stock.move.line can inject our extra columns
        """
        pickings = self.mapped("picking_id")
        if pickings:
            # Incoming receipts: create/patch move lines with lot_name + attributes
            pickings.filtered(lambda p: p.picking_type_code == "incoming")._tf_prefill_incoming_from_sale_serial_plan()
            # Internal transfers: after lots exist, prefill lot_id lines (safe if nothing to do)
            pickings.filtered(lambda p: p.picking_type_code == "internal")._tf_prefill_internal_from_sale_serial_plan_lots()

        # Make sure our extra columns appear in the modal list
        return super(StockMove, self.with_context(tf_serial_attrs=1)).action_show_details()
