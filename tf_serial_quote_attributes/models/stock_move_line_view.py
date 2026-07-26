# -*- coding: utf-8 -*-
from odoo import api, models

try:
    from lxml import etree
except Exception:
    etree = None


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        """Dynamically inject our extra columns into the Detailed Operations modal.

        Odoo 17+ uses `_get_view` (not fields_view_get). In Odoo 19, the Detailed
        Operations modal is rendered by the stock move action and the exact view id
        can differ between installations.

        We avoid brittle XMLID inheritance by inserting the columns at runtime when
        a context flag is set by `stock.move.action_show_details()`.
        """
        arch, view = super()._get_view(view_id=view_id, view_type=view_type, **options)
        if not etree:
            return arch, view

        if not self.env.context.get('tf_serial_attrs'):
            return arch, view

        # Depending on version/config, list view_type can be 'list' or 'tree'
        if view_type not in ('list', 'tree'):
            return arch, view

        try:
            doc = etree.fromstring(arch)
        except Exception:
            return arch, view

        # Helper: check if a field is already present
        def has_field(fname):
            return bool(doc.xpath(".//field[@name='%s']" % fname))

        # Ensure the helper boolean exists for readonly expression
        if not has_field('tf_allow_receipt_edit'):
            helper = etree.Element('field', name='tf_allow_receipt_edit')
            helper.set('invisible', '1')
            # Insert near the beginning
            first_field = doc.xpath('.//field')[0:1]
            if first_field:
                first_field[0].addprevious(helper)
            else:
                doc.insert(0, helper)

        # Find a good anchor: after lot field if present
        anchor = None
        for key in ('lot_name', 'lot_id'):
            nodes = doc.xpath(".//field[@name='%s']" % key)
            if nodes:
                anchor = nodes[0]
                break
        if anchor is None:
            nodes = doc.xpath(".//field[@name='location_dest_id']")
            anchor = nodes[0] if nodes else None

        if anchor is None:
            return arch, view

        # Insert columns if not already present
        columns = [
            ('tf_description', 'Description'),
            ('tf_length', 'L'),
            ('tf_width', 'W'),
            ('tf_height', 'H'),
            ('tf_dimension_unit', 'Units'),
            ('tf_weight', 'Weight'),
            ('tf_weight_unit', 'Units'),
            ('tf_storage_rate', 'Storage Rate'),
            ('tf_location_note', 'Location'),
        ]

        current = anchor
        for fname, label in columns:
            if has_field(fname):
                continue
            node = etree.Element('field', name=fname)
            node.set('string', label)
            # Editable only on incoming receipts before validate
            node.set('readonly', 'not tf_allow_receipt_edit')
            current.addnext(node)
            current = node

        arch = etree.tostring(doc, encoding='unicode')
        return arch, view
