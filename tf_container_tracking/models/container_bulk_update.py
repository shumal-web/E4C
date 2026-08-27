# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError

from .sale_serial_plan import INTERNAL_STATUS_SELECTION, CONTAINER_STATUS_SELECTION


class TfContainerBulkUpdateWizard(models.TransientModel):
    _name = "tf.container.bulk.update.wizard"
    _description = "Bulk Update Container Tracking"

    tf_internal_status = fields.Selection(INTERNAL_STATUS_SELECTION, string="Internal Status")
    tf_container_status = fields.Selection(CONTAINER_STATUS_SELECTION, string="Container Status")
    tf_eta = fields.Date(string="ETA")
    tf_lfd = fields.Date(string="LFD")

    def action_apply(self):
        self.ensure_one()
        active_ids = self.env.context.get("active_ids") or []
        containers = self.env["tf.sale.serial.plan"].browse(active_ids).exists().filtered("tf_is_container_product")
        if not containers:
            raise UserError(_("Please select at least one container tracking record."))

        values = {}
        if self.tf_internal_status:
            values["tf_internal_status"] = self.tf_internal_status
        if self.tf_container_status:
            values["tf_container_status"] = self.tf_container_status
        if self.tf_eta:
            values["tf_eta"] = self.tf_eta
        if self.tf_lfd:
            values["tf_lfd"] = self.tf_lfd
        if not values:
            raise UserError(_("Please set at least one value to update."))

        containers.write(values)
        return {"type": "ir.actions.act_window_close"}
