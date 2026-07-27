# -*- coding: utf-8 -*-
from odoo import api, fields, models


class TfDispatchTicket(models.Model):
    _inherit = "tf.dispatch.ticket"

    tf_special_instructions = fields.Text(
        string="Special Instructions",
        related="sale_order_id.tf_special_instructions",
        readonly=False,
        store=True,
    )

    @api.depends(
        "sale_order_id",
        "container_plan_id",
        "location_partner_id",
        "location_note",
        "truck_id",
        "driver_id",
        "trailer_id",
        "dispatch_date",
        "trailer_destination_location",
        "tf_special_instructions",
    )
    def _compute_whatsapp_message_preview(self):
        super()._compute_whatsapp_message_preview()
        for rec in self:
            if rec.tf_special_instructions and rec.whatsapp_message_preview:
                rec.whatsapp_message_preview = (
                    f"{rec.whatsapp_message_preview}\n"
                    f"Special Instructions: {rec.tf_special_instructions}"
                )
