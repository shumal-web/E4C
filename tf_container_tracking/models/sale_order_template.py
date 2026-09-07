# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrderTemplate(models.Model):
    _inherit = "sale.order.template"

    tf_shipment_type = fields.Selection(
        [
            ("import", "Import"),
            ("export", "Export"),
        ],
        string="Flow Type",
        default="import",
        required=True,
        help="Default import/export flow applied when this template is selected on a quotation.",
    )
    tf_address_note = fields.Text(
        string="Address",
        help="Default address copied to quotations created from this template.",
    )
    tf_shipper_partner_id = fields.Many2one(
        "res.partner",
        string="Shipper Address",
        help="Default shipper contact/address copied to quotations created from this template.",
    )
    tf_shipper_note = fields.Text(
        string="Shipper",
        help="Default shipper details copied to quotations created from this template.",
    )
    tf_consignee_partner_id = fields.Many2one(
        "res.partner",
        string="Consignee Address",
        help="Default consignee contact/address copied to quotations created from this template.",
    )
    tf_consignee_note = fields.Text(
        string="Consignee",
        help="Default consignee details copied to quotations created from this template.",
    )
    tf_special_instructions = fields.Text(
        string="Special Instructions",
        help="Default special request/instructions copied to quotations created from this template.",
    )

    def _tf_partner_address_text(self, partner):
        if not partner:
            return False
        values = [partner.display_name]
        address = partner._display_address(without_company=True)
        if address:
            values.append(address)
        return "\n".join(dict.fromkeys([value for value in values if value]))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("tf_shipper_partner_id") and not vals.get("tf_shipper_note"):
                vals["tf_shipper_note"] = self._tf_partner_address_text(
                    self.env["res.partner"].browse(vals["tf_shipper_partner_id"])
                )
            if vals.get("tf_consignee_partner_id") and not vals.get("tf_consignee_note"):
                vals["tf_consignee_note"] = self._tf_partner_address_text(
                    self.env["res.partner"].browse(vals["tf_consignee_partner_id"])
                )
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("tf_shipper_partner_id") and "tf_shipper_note" not in vals:
            vals = dict(
                vals,
                tf_shipper_note=self._tf_partner_address_text(
                    self.env["res.partner"].browse(vals["tf_shipper_partner_id"])
                ),
            )
        if vals.get("tf_consignee_partner_id") and "tf_consignee_note" not in vals:
            vals = dict(
                vals,
                tf_consignee_note=self._tf_partner_address_text(
                    self.env["res.partner"].browse(vals["tf_consignee_partner_id"])
                ),
            )
        return super().write(vals)

    @api.onchange("tf_shipper_partner_id")
    def _onchange_tf_shipper_partner_id(self):
        for template in self:
            if template.tf_shipper_partner_id:
                template.tf_shipper_note = template._tf_partner_address_text(template.tf_shipper_partner_id)

    @api.onchange("tf_consignee_partner_id")
    def _onchange_tf_consignee_partner_id(self):
        for template in self:
            if template.tf_consignee_partner_id:
                template.tf_consignee_note = template._tf_partner_address_text(template.tf_consignee_partner_id)
