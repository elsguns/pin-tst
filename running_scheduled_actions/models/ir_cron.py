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

    @api.model
    def web_search_read(self, domain, specification, offset=0, limit=None, order=None, count_limit=None):
        # Non-stored field can't be sorted via SQL — handle in Python when
        # the user clicks the Running column header.
        if order and order.split(',')[0].strip().split()[0] == 'is_running':
            desc = 'desc' in order.split(',')[0].lower()
            records = self.search(domain or [])
            records._compute_is_running()
            sorted_ids = records.sorted('is_running', reverse=desc).ids
            paginated_ids = sorted_ids[offset:(offset + limit) if limit else None]
            result = super().web_search_read(
                [('id', 'in', paginated_ids)], specification,
                offset=0, limit=None, order=None, count_limit=count_limit,
            )
            id_to_record = {r['id']: r for r in result['records']}
            result['records'] = [id_to_record[i] for i in paginated_ids if i in id_to_record]
            result['length'] = len(records)
            return result
        return super().web_search_read(
            domain, specification, offset=offset, limit=limit, order=order, count_limit=count_limit,
        )
