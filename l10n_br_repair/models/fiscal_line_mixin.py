# Copyright 2021 - TODAY, Marcel Savegnago - Escodoo
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import odoo.addons.decimal_precision as dp


class FiscalLineMixin(models.AbstractModel):
    _name = 'l10n_br_repair.fiscal.line.mixin'
    _inherit = ['l10n_br_fiscal.document.line.mixin']
    _description = 'Fiscal Line Mixin'

    @api.model
    def _default_fiscal_operation(self):
        return self.env.user.company_id.repair_fiscal_operation_id

    fiscal_operation_id = fields.Many2one(
        comodel_name='l10n_br_fiscal.operation',
        default=_default_fiscal_operation,
        domain=lambda self: self._fiscal_operation_domain())

    price_gross = fields.Monetary(
        compute='_compute_price_subtotal',
        string='Gross Amount',
        default=0.00,
    )

    price_tax = fields.Monetary(
        compute='_compute_price_subtotal',
        string='Price Tax',
        default=0.00,
    )

    price_total = fields.Monetary(
        compute='_compute_price_subtotal',
        string='Price Total',
        default=0.00,
    )

    discount = fields.Float(
        string='Discount (%)',
    )

    price_subtotal = fields.Float(
        'Subtotal',
        compute='_compute_price_subtotal',
        digits=dp.get_precision('Account'))

    @api.model
    def _fiscal_operation_domain(self):
        domain = [('state', '=', 'approved')]
        return domain

    def _get_protected_fields(self):
        protected_fields = super()._get_protected_fields()
        return protected_fields + [
            'fiscal_tax_ids', 'fiscal_operation_id',
            'fiscal_operation_line_id',
        ]

    @api.depends(
        'product_uom_qty',
        'price_unit',
        'discount',
        'fiscal_price',
        'fiscal_quantity',
        'discount_value',
        'freight_value',
        'insurance_value',
        'other_costs_value',
        'tax_id')
    def _compute_price_subtotal(self):
        super()._compute_price_subtotal()
        for l in self:
            l._update_taxes()
            price_tax = l.price_tax + l.amount_tax_not_included
            price_total = (
                l.price_subtotal + l.freight_value +
                l.insurance_value + l.other_costs_value)

            price_subtotal = (
                l.price_subtotal * (1 - (l.discount or 0.0) / 100.0)
            )

            l.update({
                'price_tax': price_tax,
                'price_gross': price_subtotal + l.discount_value,
                'price_total': price_total + price_tax,
                'price_subtotal': price_subtotal,
            })

    @api.multi
    def _prepare_invoice_line(self, qty):
        self.ensure_one()
        res = {}
        product = self.product_id.with_context(force_company=self.company_id.id)
        account = \
            product.property_account_income_id or \
            product.categ_id.property_account_income_categ_id

        if not account and self.product_id:
            raise UserError(_('Please define income account for this product: '
                              '"%s" (id:%d) - or for its category: "%s".') %
                            (self.product_id.name,
                             self.product_id.id,
                             self.product_id.categ_id.name))

        # fpos = self.repair_id.partner_id.property_account_position_id.id or self.env[
        #     'account.fiscal.position'].get_fiscal_position(
        #     self.repair_id.partner_id.id, delivery_id=self.repair_id.address_id.id)

        # if fpos and account:
        #     account = fpos.map_tax(account)

        res = {
            'name': self.name,
            'origin': self.repair_id.name,
            'account_id': account.id,
            'price_unit': self.price_unit,
            'quantity': qty,
            'discount': self.discount,
            'uom_id': self.product_uom.id,
            'product_id': self.product_id.id or False,
            'invoice_line_tax_ids': [(6, 0, self.tax_id.ids)],
        }

        res.update(self._prepare_br_fiscal_dict())
        return res

    @api.onchange('product_uom', 'product_uom_qty')
    def _onchange_product_uom(self):
        """To call the method in the mixin to update
        the price and fiscal quantity."""
        self._onchange_commercial_quantity()

    @api.onchange('discount', 'product_uom_qty', 'price_unit')
    def _onchange_discount_percent(self):
        """Update discount value"""
        if not self.env.user.has_group('l10n_br_repair.group_discount_per_value'):
            if self.discount:
                self.discount_value = (
                    (self.product_uom_qty * self.price_unit)
                    * (self.discount / 100)
                )

    @api.onchange('discount_value')
    def _onchange_discount_value(self):
        """Update discount percent"""
        if self.env.user.has_group('l10n_br_repair.group_discount_per_value'):
            if self.discount_value:
                self.discount = ((self.discount_value * 100) /
                                 (self.product_uom_qty * self.price_unit))

    @api.onchange('fiscal_tax_ids')
    def _onchange_fiscal_tax_ids(self):
        super()._onchange_fiscal_tax_ids()
        self.tax_id |= self.fiscal_tax_ids.account_taxes()