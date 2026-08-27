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
    tf_sale_tag_ids = fields.Many2many(
        string="Tags",
        related="sale_order_id.tag_ids",
        readonly=True,
    )

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
        "tf_special_instructions",
        "tf_sale_tag_ids",
    )
    def _compute_whatsapp_message_preview(self):
        super()._compute_whatsapp_message_preview()
        for rec in self:
            if rec.tf_special_instructions and rec.whatsapp_message_preview:
                rec.whatsapp_message_preview = (
                    f"{rec.whatsapp_message_preview}\n"
                    f"Special Instructions: {rec.tf_special_instructions}"
                )
            if rec.tf_sale_tag_ids and rec.whatsapp_message_preview:
                tag_names = ", ".join(rec.tf_sale_tag_ids.mapped("name"))
                rec.whatsapp_message_preview = f"{rec.whatsapp_message_preview}\nTags: {tag_names}"
