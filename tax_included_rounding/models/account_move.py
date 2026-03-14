from odoo import models, api
from odoo.tools import float_round
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _get_tax_groups_invoice(self):
        """
        Group invoice lines by tax rate.
        Returns a dict: {tax_rate: {'tax': tax_record, 'lines': [lines]}}
        Returns None if any line has non-included taxes or no taxes.
        """
        self.ensure_one()
        tax_groups = {}
        
        for line in self.invoice_line_ids:
            if line.display_type:  # Skip section/note lines
                continue
            
            if not line.tax_ids:
                # Line without tax - can't handle this
                return None
            
            # For simplicity, take the first tax on the line
            tax = line.tax_ids[0]
            
            if not tax.price_include or tax.amount_type != 'percent':
                # Non-included tax or non-percentage - fall back to standard
                return None
            
            tax_rate = tax.amount / 100
            
            if tax_rate not in tax_groups:
                tax_groups[tax_rate] = {
                    'tax': tax,
                    'lines': [],
                }
            
            tax_groups[tax_rate]['lines'].append(line)
        
        return tax_groups if tax_groups else None

    @api.depends('invoice_line_ids.tax_ids', 'invoice_line_ids.price_total', 'partner_id', 'currency_id', 'company_id')
    def _compute_tax_totals(self):
        for move in self:
            # Only apply to customer invoices and vendor bills
            if move.move_type not in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                super(AccountMove, move)._compute_tax_totals()
                continue
            
            tax_groups = move._get_tax_groups_invoice()
            
            if tax_groups is None:
                # Can't handle - use standard calculation
                super(AccountMove, move)._compute_tax_totals()
                continue
            
            rounding = move.currency_id.rounding
            
            # Calculate per tax group
            total_untaxed = 0
            total_tax = 0
            total_incl = 0
            groups_by_subtotal = []
            
            for tax_rate, group_data in tax_groups.items():
                tax = group_data['tax']
                lines = group_data['lines']
                
                # Sum the tax-included totals for this group
                group_total_incl = sum(line.price_total for line in lines)
                
                # Calculate untaxed: base = total / (1 + rate)
                group_untaxed = float_round(
                    group_total_incl / (1 + tax_rate),
                    precision_rounding=rounding
                )
                
                # Tax is the difference
                group_tax = float_round(
                    group_total_incl - group_untaxed,
                    precision_rounding=rounding
                )
                
                total_untaxed += group_untaxed
                total_tax += group_tax
                total_incl += group_total_incl
                
                # Get the tax group id for proper display
                tax_group_id = tax.tax_group_id.id if tax.tax_group_id else tax.id
                tax_group_name = tax.tax_group_id.name if tax.tax_group_id else tax.name
                
                groups_by_subtotal.append({
                    'tax_group_name': tax_group_name,
                    'tax_group_amount': abs(group_tax),
                    'tax_group_base_amount': abs(group_untaxed),
                    'formatted_tax_group_amount': move.currency_id.format(abs(group_tax)),
                    'formatted_tax_group_base_amount': move.currency_id.format(abs(group_untaxed)),
                    'tax_group_id': tax_group_id,
                    'group_key': f'Untaxed Amount-{tax_group_id}',
                })
                
                _logger.info(
                    "Tax Included Rounding Fix: invoice %s - group %s (%.2f%%): incl=%.2f, untaxed=%.2f, tax=%.2f",
                    move.name, tax_group_name, tax_rate * 100, group_total_incl, group_untaxed, group_tax
                )
            
            # Build the tax_totals structure
            move.tax_totals = {
                'amount_total': abs(total_incl),
                'amount_untaxed': abs(total_untaxed),
                'formatted_amount_total': move.currency_id.format(abs(total_incl)),
                'formatted_amount_untaxed': move.currency_id.format(abs(total_untaxed)),
                'groups_by_subtotal': {
                    'Untaxed Amount': groups_by_subtotal,
                },
                'subtotals': [{
                    'name': 'Untaxed Amount',
                    'amount': abs(total_untaxed),
                    'formatted_amount': move.currency_id.format(abs(total_untaxed)),
                }],
                'subtotals_order': ['Untaxed Amount'],
                'allow_tax_edition': False,
                'display_tax_base': True,
            }
