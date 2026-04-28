import psycopg2
from odoo import api, fields, models


class IrCron(models.Model):
    _inherit = 'ir.cron'

    is_running = fields.Boolean(
        string='Running',
        compute='_compute_is_running',
        search='_search_is_running',
    )

    def _compute_is_running(self):
        not_running = set()
        for cron_id in self.ids:
            sp = f'cron_check_{cron_id}'
            self.env.cr.execute(f'SAVEPOINT "{sp}"')
            try:
                self.env.cr.execute(
                    'SELECT id FROM ir_cron WHERE id = %s FOR UPDATE NOWAIT',
                    [cron_id],
                )
                not_running.add(cron_id)
            except psycopg2.errors.LockNotAvailable:
                pass
            finally:
                self.env.cr.execute(f'ROLLBACK TO SAVEPOINT "{sp}"')
        for cron in self:
            cron.is_running = bool(cron.id) and cron.id not in not_running

    @api.model
    def _search_is_running(self, operator, value):
        if operator not in ('=', '!='):
            return [('id', 'in', [])]
        all_crons = self.sudo().with_context(active_test=False).search([])
        all_crons._compute_is_running()
        running_ids = all_crons.filtered('is_running').ids
        match_running = (operator == '=' and bool(value)) or (operator == '!=' and not bool(value))
        return [('id', 'in' if match_running else 'not in', running_ids)]
