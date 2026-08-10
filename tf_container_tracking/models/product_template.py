# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = "product.template"

    tf_is_container = fields.Boolean(
        string="Is Container Product",
        help="Enable this for container products that must be tracked as unique serials.",
    )
    tf_requires_container = fields.Boolean(
        string="Requires Container Assignment",
        help="For serial-tracked piece products that must be linked to a container serial.",
    )
    tf_direct_container_to_client = fields.Boolean(
        string="Direct Container to Client",
        help="Use this on service/flow products that should move the container directly to the client without a warehouse stop.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "type" in fields_list:
            res["type"] = "service"
        return res

    def _tf_apply_logistics_product_defaults(self, vals):
        if vals.get("tf_is_container"):
            vals["tf_requires_container"] = False
        if vals.get("tf_is_container") or vals.get("tf_requires_container"):
            vals.setdefault("tracking", "serial")
            vals.setdefault("type", "consu")
            vals.setdefault("is_storable", True)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for vals in vals_list:
            vals = self._tf_apply_logistics_product_defaults(dict(vals))
            vals.setdefault("type", "service")
            prepared_vals.append(vals)
        vals_list = prepared_vals
        return super().create(vals_list)

    def write(self, vals):
        vals = self._tf_apply_logistics_product_defaults(dict(vals))
        return super().write(vals)

    @api.onchange("tf_is_container", "tf_requires_container")
    def _onchange_tf_container_flags(self):
        for product in self:
            if product.tf_is_container:
                product.tf_requires_container = False
            if product.tf_is_container or product.tf_requires_container:
                product.tracking = "serial"
                product.type = "consu"
                product.is_storable = True

    @api.constrains("tf_is_container", "tf_requires_container", "tracking")
    def _check_tf_container_flags(self):
        for product in self:
            if product.tf_is_container and product.tf_requires_container:
                raise ValidationError(
                    _("A product cannot be both a container product and require container assignment.")
                )
            if (product.tf_is_container or product.tf_requires_container) and product.tracking != "serial":
                raise ValidationError(
                    _("Container and container-required products must be tracked by unique serial number.")
                )
