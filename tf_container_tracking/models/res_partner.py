# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    tf_credit_limit = fields.Monetary(
        string="E4C Credit Limit",
        currency_field="currency_id",
        copy=False,
        tracking=True,
        help="Internal E4C credit limit used for the dispatch/container sales flow.",
    )
    tf_credit_used = fields.Monetary(
        string="E4C Credit Used",
        currency_field="currency_id",
        compute="_compute_tf_credit_amounts",
        help="Total open E4C sales credit for this customer. Cleared orders are excluded.",
    )
    tf_credit_available = fields.Monetary(
        string="E4C Credit Available",
        currency_field="currency_id",
        compute="_compute_tf_credit_amounts",
    )
    tf_credit_over_limit = fields.Boolean(
        string="Over E4C Credit Limit",
        compute="_compute_tf_credit_amounts",
    )

    def _tf_credit_order_domain(self):
        return [
            ("partner_id", "child_of", self.commercial_partner_id.ids),
            ("state", "in", ("sale", "done")),
            ("tf_credit_state", "!=", "cleared"),
        ]

    @api.depends("tf_credit_limit", "sale_order_ids.amount_total", "sale_order_ids.tf_credit_state")
    @api.depends_context("company")
    def _compute_tf_credit_amounts(self):
        today = fields.Date.context_today(self)
        SaleOrder = self.env["sale.order"].sudo()
        company = self.env.company
        for partner in self:
            currency = partner.currency_id or company.currency_id
            orders = SaleOrder.search(partner._tf_credit_order_domain()) if partner.commercial_partner_id else SaleOrder
            used = 0.0
            for order in orders:
                order_company = order.company_id or company
                used += order.currency_id._convert(
                    order.amount_total,
                    currency,
                    order_company,
                    today,
                )
            partner.tf_credit_used = used
            partner.tf_credit_available = (partner.tf_credit_limit or 0.0) - used
            partner.tf_credit_over_limit = bool(partner.tf_credit_limit and used > partner.tf_credit_limit)

    def action_tf_clear_credit_now(self):
        SaleOrder = self.env["sale.order"]
        for partner in self:
            orders = SaleOrder.search(partner._tf_credit_order_domain())
            orders.action_tf_clear_credit()
        return True
