# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class TfLoadDocument(models.Model):
    _name = "tf.load.document"
    _description = "E4C Load Document"
    _order = "uploaded_on desc, id desc"
    _rec_name = "file_name"

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Sales Order",
        required=True,
        index=True,
        ondelete="cascade",
    )
    container_plan_id = fields.Many2one(
        "tf.sale.serial.plan",
        string="Container",
        index=True,
        ondelete="set null",
        domain="[('order_id', '=', sale_order_id), ('tf_is_container_product', '=', True)]",
    )
    dispatch_ticket_id = fields.Many2one(
        "tf.dispatch.ticket",
        string="Dispatch Ticket",
        index=True,
        ondelete="set null",
        domain="[('sale_order_id', '=', sale_order_id)]",
    )
    picking_id = fields.Many2one(
        "stock.picking",
        string="Inventory Document",
        index=True,
        ondelete="set null",
        domain="[('tf_sale_order_id', '=', sale_order_id)]",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        related="sale_order_id.company_id",
        store=True,
        readonly=True,
    )
    document_type = fields.Selection(
        [
            ("general", "General"),
            ("bol", "BOL"),
            ("customs", "Customs"),
            ("packing_list", "Packing List"),
            ("invoice", "Invoice"),
            ("photo", "Photo"),
            ("client_email", "Client Email"),
            ("other", "Other"),
        ],
        string="Document Type",
        default="general",
        required=True,
    )
    attachment_id = fields.Many2one(
        "ir.attachment",
        string="Chatter Attachment",
        index=True,
        ondelete="cascade",
        copy=False,
        help="Original Odoo attachment when the file was uploaded from chatter.",
    )
    file_data = fields.Binary(
        string="Upload / Replace File",
        attachment=True,
    )
    file_name = fields.Char(
        string="File Name",
        required=True,
    )
    uploaded_by_id = fields.Many2one(
        "res.users",
        string="Uploaded By",
        default=lambda self: self.env.user,
        readonly=True,
        copy=False,
    )
    uploaded_on = fields.Datetime(
        string="Uploaded On",
        default=fields.Datetime.now,
        readonly=True,
        copy=False,
    )
    comment = fields.Text(string="Comment")
    source = fields.Char(
        string="Uploaded From",
        compute="_compute_source",
    )

    _attachment_unique = models.Constraint(
        "UNIQUE(attachment_id)",
        "This chatter attachment is already linked to a load document.",
    )

    @api.depends("container_plan_id", "dispatch_ticket_id", "picking_id")
    def _compute_source(self):
        for document in self:
            if document.container_plan_id:
                document.source = "Container Tracking"
            elif document.dispatch_ticket_id:
                document.source = "Dispatch Ticket"
            elif document.picking_id:
                document.source = "Inventory Document"
            else:
                document.source = "Sales Order"

    @api.constrains("attachment_id", "file_data")
    def _check_file_source(self):
        for document in self:
            if not document.attachment_id and not document.file_data:
                raise ValidationError(_("Please upload a file or link a chatter attachment."))

    @api.model
    def _tf_sale_order_from_vals(self, vals):
        if vals.get("sale_order_id"):
            return vals["sale_order_id"]

        if vals.get("container_plan_id"):
            container = self.env["tf.sale.serial.plan"].browse(vals["container_plan_id"]).exists()
            if container.order_id:
                return container.order_id.id

        if vals.get("dispatch_ticket_id"):
            dispatch = self.env["tf.dispatch.ticket"].browse(vals["dispatch_ticket_id"]).exists()
            if dispatch.sale_order_id:
                return dispatch.sale_order_id.id

        if vals.get("picking_id"):
            picking = self.env["stock.picking"].browse(vals["picking_id"]).exists()
            sale_order = picking.tf_sale_order_id or picking.sale_id
            if sale_order:
                return sale_order.id

        return False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            attachment = self.env["ir.attachment"].browse(vals.get("attachment_id")).exists()
            if attachment:
                vals.setdefault("file_name", attachment.name or _("Attachment"))
                vals.setdefault("uploaded_by_id", attachment.create_uid.id or self.env.user.id)
                vals.setdefault("uploaded_on", attachment.create_date or fields.Datetime.now())

            sale_order_id = self._tf_sale_order_from_vals(vals)
            if sale_order_id and not vals.get("sale_order_id"):
                vals["sale_order_id"] = sale_order_id
            vals.setdefault("uploaded_by_id", self.env.user.id)
            vals.setdefault("uploaded_on", fields.Datetime.now())
        return super().create(vals_list)

    def action_download_file(self):
        self.ensure_one()
        if self.attachment_id:
            attachment = self.attachment_id
            if attachment.type == "url" and attachment.url:
                return {
                    "type": "ir.actions.act_url",
                    "url": attachment.url,
                    "target": "new",
                }
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content/{attachment.id}?download=true",
                "target": "self",
            }
        if self.file_data:
            return {
                "type": "ir.actions.act_url",
                "url": f"/web/content?model={self._name}&id={self.id}&field=file_data&filename_field=file_name&download=true",
                "target": "self",
            }
        raise UserError(_("No file is linked to this document."))
