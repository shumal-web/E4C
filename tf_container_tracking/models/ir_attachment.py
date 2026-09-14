# -*- coding: utf-8 -*-
from odoo import api, fields, models


SUPPORTED_LOAD_DOCUMENT_MODELS = (
    "sale.order",
    "tf.sale.serial.plan",
    "tf.dispatch.ticket",
    "stock.picking",
)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _tf_load_document_link_vals(self):
        self.ensure_one()
        if self.res_field:
            return False

        vals = {}
        if self.res_model not in SUPPORTED_LOAD_DOCUMENT_MODELS:
            return False

        if self.res_model == "sale.order" and self.res_id:
            sale_order = self.env["sale.order"].sudo().browse(self.res_id).exists()
            if sale_order:
                vals["sale_order_id"] = sale_order.id
        elif self.res_model == "tf.sale.serial.plan" and self.res_id:
            container = self.env["tf.sale.serial.plan"].sudo().browse(self.res_id).exists()
            if container and container.order_id:
                vals.update({
                    "sale_order_id": container.order_id.id,
                    "container_plan_id": container.id,
                })
        elif self.res_model == "tf.dispatch.ticket" and self.res_id:
            dispatch = self.env["tf.dispatch.ticket"].sudo().browse(self.res_id).exists()
            if dispatch and dispatch.sale_order_id:
                vals.update({
                    "sale_order_id": dispatch.sale_order_id.id,
                    "dispatch_ticket_id": dispatch.id,
                })
        elif self.res_model == "stock.picking" and self.res_id:
            picking = self.env["stock.picking"].sudo().browse(self.res_id).exists()
            sale_order = picking.tf_sale_order_id or picking.sale_id if picking else False
            if sale_order:
                vals.update({
                    "sale_order_id": sale_order.id,
                    "picking_id": picking.id,
                })

        return vals or False

    def _tf_sync_load_documents(self):
        if self.env.context.get("tf_skip_load_document_sync"):
            return

        Document = self.env["tf.load.document"].sudo().with_context(tf_skip_load_document_sync=True)
        for attachment in self.sudo():
            vals = attachment._tf_load_document_link_vals()
            if not vals:
                continue

            document = Document.search([("attachment_id", "=", attachment.id)], limit=1)
            sync_vals = {
                **vals,
                "attachment_id": attachment.id,
                "file_name": attachment.name or "Attachment",
            }
            if document:
                document.write(sync_vals)
            else:
                Document.create({
                    **sync_vals,
                    "document_type": "photo" if (attachment.mimetype or "").startswith("image/") else "general",
                    "uploaded_by_id": attachment.create_uid.id or self.env.uid,
                    "uploaded_on": attachment.create_date or fields.Datetime.now(),
                    "comment": attachment.description or False,
                })

    @api.model
    def _cron_tf_sync_load_documents(self, limit=500):
        """Backfill chatter files uploaded before the live sync existed."""
        query = """
            SELECT attachment.id
              FROM ir_attachment attachment
         LEFT JOIN tf_load_document document
                ON document.attachment_id = attachment.id
             WHERE attachment.res_field IS NULL
               AND attachment.res_model = ANY(%s)
               AND COALESCE(attachment.res_id, 0) != 0
               AND document.id IS NULL
          ORDER BY attachment.id DESC
             LIMIT %s
        """
        self.env.cr.execute(query, (list(SUPPORTED_LOAD_DOCUMENT_MODELS), limit))
        attachment_ids = [row[0] for row in self.env.cr.fetchall()]
        if attachment_ids:
            self.browse(attachment_ids)._tf_sync_load_documents()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        attachments._tf_sync_load_documents()
        return attachments

    def write(self, vals):
        result = super().write(vals)
        if {"res_model", "res_id", "name", "description", "type", "url", "mimetype"}.intersection(vals):
            self._tf_sync_load_documents()
        return result

    def unlink(self):
        documents = self.env["tf.load.document"].sudo().search([("attachment_id", "in", self.ids)])
        documents.unlink()
        return super().unlink()
