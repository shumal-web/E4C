# -*- coding: utf-8 -*-
from datetime import date, datetime

from odoo import fields


DIMENSION_FIELDS = ("tf_length", "tf_width", "tf_height")


def safe_get(record, field_name, default=False):
    if record and field_name in record._fields:
        return record[field_name]
    return default


def text_value(value):
    if not value:
        return ""
    return str(value).strip()


def partner_address(partner):
    if not partner:
        return ""
    return (partner._display_address(without_company=False) or "").strip()


def selection_label(record, field_name, value):
    if not value or not record or field_name not in record._fields:
        return text_value(value)
    selection = record._fields[field_name].selection
    if callable(selection):
        selection = selection(record)
    return dict(selection).get(value, value)


def format_number(value):
    if value in (False, None, ""):
        return ""
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


def format_quantity(value):
    if value in (False, None, ""):
        return "0"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return ("%.2f" % number).rstrip("0").rstrip(".")


def format_date(record, value):
    if not value:
        return ""
    if isinstance(value, datetime):
        value = fields.Datetime.context_timestamp(record, value)
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")
    return text_value(value)


def format_datetime(record, value):
    if not value:
        return ""
    if isinstance(value, datetime):
        value = fields.Datetime.context_timestamp(record, value)
        return value.strftime("%Y-%m-%d %H:%M")
    return format_date(record, value)


def dimension_text(source):
    values = [format_number(safe_get(source, field_name)) for field_name in DIMENSION_FIELDS]
    if not any(values):
        return ""
    unit = text_value(safe_get(source, "tf_dimension_unit"))
    dim = " x ".join(value or "0" for value in values)
    return "%s %s" % (dim, unit) if unit else dim


def weight_text(source):
    weight = format_number(safe_get(source, "tf_weight"))
    if not weight:
        return ""
    unit = text_value(safe_get(source, "tf_weight_unit"))
    return "%s %s" % (weight, unit) if unit else weight


def container_plan_label(container_plan):
    if not container_plan:
        return ""
    return text_value(
        safe_get(container_plan, "tf_container_number")
        or safe_get(container_plan, "serial_name")
        or container_plan.display_name
    )


def container_lot_label(lot):
    if not lot:
        return ""
    container_lot = safe_get(lot, "tf_container_lot_id")
    if container_lot:
        return text_value(container_lot.name)
    return ""


def move_line_container_label(move_line):
    container_plan = safe_get(move_line, "tf_container_plan_id")
    if container_plan:
        return container_plan_label(container_plan)
    return container_lot_label(move_line.lot_id)


def move_line_source(move_line):
    return move_line.lot_id or safe_get(move_line, "tf_sale_serial_plan_id") or move_line


def move_line_serial_name(move_line):
    return text_value(
        (move_line.lot_id.name if move_line.lot_id else False)
        or safe_get(move_line, "lot_name")
        or safe_get(safe_get(move_line, "tf_sale_serial_plan_id"), "serial_name")
    )
