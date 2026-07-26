# -*- coding: utf-8 -*-
from odoo import api, models

try:
    from lxml import etree
except Exception:
    etree = None


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if not etree or not self.env.context.get("tf_serial_attrs"):
            return arch, view
        if view_type not in ("list", "tree"):
            return arch, view

        try:
            doc = etree.fromstring(arch)
        except Exception:
            return arch, view

        helper_names = {"tf_hide_container_columns"}
        existing_fields = {
            node.get("name")
            for node in doc.xpath(".//field[@name]")
            if node.get("name")
        }
        for helper_name in helper_names - existing_fields:
            helper = etree.Element("field", name=helper_name)
            helper.set("invisible", "1")
            first_field = doc.xpath(".//field")[0:1]
            if first_field:
                first_field[0].addprevious(helper)
            else:
                doc.insert(0, helper)

        if doc.xpath(".//field[@name='tf_container_plan_id']"):
            return etree.tostring(doc, encoding="unicode"), view

        anchors = doc.xpath(".//field[@name='tf_location_note']")
        if not anchors:
            anchors = doc.xpath(".//field[@name='lot_name'] | .//field[@name='lot_id']")
        if not anchors:
            return arch, view

        node = etree.Element("field", name="tf_container_plan_id")
        node.set("string", "Container")
        node.set("invisible", "tf_hide_container_columns")
        node.set("readonly", "not tf_allow_receipt_edit")
        node.set("can_create", "0")
        node.set("can_write", "0")
        node.set("context", "{'create': False}")
        node.set("options", "{'no_create': True, 'no_create_edit': True, 'no_open': True}")
        anchors[0].addnext(node)

        return etree.tostring(doc, encoding="unicode"), view
