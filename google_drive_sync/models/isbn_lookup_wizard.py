# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ISBNLookupWizard(models.TransientModel):
    _name = 'gdrive.isbn.lookup.wizard'
    _description = 'ISBN Lookup on Google Drive'

    # Step 1: Upload
    csv_file = fields.Binary('CSV File')
    csv_filename = fields.Char('Filename')

    # Step 2: Results
    state = fields.Selection([
        ('upload', 'Upload'),
        ('results', 'Results'),
    ], default='upload', string='State')

    result_ids = fields.One2many('gdrive.isbn.lookup.result', 'wizard_id', string='Results')

    # Summary
    total_isbns_scanned = fields.Integer('Total ISBNs Scanned', readonly=True)
    total_matched = fields.Integer('ISBNs with Files', compute='_compute_stats', store=False)
    total_files = fields.Integer('Total Files', compute='_compute_stats', store=False)
    total_not_found = fields.Integer('ISBNs Not Found', compute='_compute_stats', store=False)
    total_already_downloaded = fields.Integer('Already Downloaded', compute='_compute_stats', store=False)

    @api.depends('result_ids', 'result_ids.file_count', 'total_isbns_scanned')
    def _compute_stats(self):
        for rec in self:
            rec.total_matched = len(rec.result_ids)
            rec.total_files = sum(rec.result_ids.mapped('file_count'))
            rec.total_not_found = rec.total_isbns_scanned - len(rec.result_ids)
            rec.total_already_downloaded = len(rec.result_ids.filtered('already_downloaded'))

    def _parse_isbns(self):
        """Parse ISBNs from the uploaded CSV file."""
        raw = base64.b64decode(self.csv_file)
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        first_line = text.split('\n')[0] if text else ''
        delimiter = ';' if ';' in first_line else ','

        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        isbns = []
        header_skipped = False
        for row in reader:
            if not row:
                continue
            val = row[0].strip().replace('-', '').replace(' ', '')
            if not header_skipped:
                header_skipped = True
                if not val.isdigit():
                    continue
            if val and val.isdigit() and len(val) >= 10:
                isbns.append(val)

        # Deduplicate, preserve order
        seen = set()
        unique = []
        for isbn in isbns:
            if isbn not in seen:
                seen.add(isbn)
                unique.append(isbn)
        return unique

    def action_scan(self):
        """Search the file registry for files matching the ISBNs."""
        self.ensure_one()

        if not self.csv_file:
            raise UserError(_('Please upload a CSV file.'))

        isbns = self._parse_isbns()
        if not isbns:
            raise UserError(_('No valid ISBNs found in the CSV file.'))

        _logger.info(f"Searching registry for {len(isbns)} ISBNs")

        # Get product content folder IDs
        product_folders = self.env['gdrive.folder.selection'].search([
            ('selected', '=', True),
            ('download_product_content', '=', True),
        ])
        if not product_folders:
            raise UserError(_('No folders are configured for Product Images & Descriptions.'))

        folder_ids = product_folders.mapped('folder_id')

        # Get all jpg/txt files from registry in these folders
        Registry = self.env['gdrive.file.registry']
        registry_files = Registry.search([
            ('folder_id', 'in', folder_ids),
            ('mime_type', 'in', ['image/jpeg', 'image/jpg', 'text/plain']),
        ])

        _logger.info(f"Registry has {len(registry_files)} jpg/txt files in product content folders")

        # Build ISBN lookup: for each file, check if it starts with an ISBN
        isbn_set = set(isbns)
        # Sort by length descending so ISBN-13 matches before ISBN-10
        sorted_isbns = sorted(isbn_set, key=len, reverse=True)

        # Group files by matched ISBN
        isbn_matches = {}  # isbn -> list of registry records

        for file_rec in registry_files:
            fname = file_rec.name or ''
            name_without_ext = fname.rsplit('.', 1)[0] if '.' in fname else fname

            # Extract leading digits
            digits = ''
            for ch in name_without_ext:
                if ch.isdigit():
                    digits += ch
                else:
                    break

            if len(digits) < 10:
                continue

            # Try ISBN-13 first, then ISBN-10
            matched_isbn = None
            if len(digits) >= 13 and digits[:13] in isbn_set:
                matched_isbn = digits[:13]
            elif digits[:10] in isbn_set:
                matched_isbn = digits[:10]

            if matched_isbn:
                if matched_isbn not in isbn_matches:
                    isbn_matches[matched_isbn] = []
                isbn_matches[matched_isbn].append(file_rec)

        _logger.info(f"Matched {len(isbn_matches)} ISBNs to registry files")

        # Create result records (only for matches)
        ResultModel = self.env['gdrive.isbn.lookup.result']
        self.result_ids.unlink()

        for isbn in isbns:
            if isbn not in isbn_matches:
                continue

            files = isbn_matches[isbn]
            registry_ids = [f.id for f in files]
            file_names = ', '.join(f.name for f in files)
            all_downloaded = all(f.is_downloaded for f in files)
            any_to_download = any(not f.is_downloaded for f in files)

            ResultModel.create({
                'wizard_id': self.id,
                'isbn': isbn,
                'file_count': len(files),
                'file_names': file_names,
                'registry_ids_str': ','.join(str(rid) for rid in registry_ids),
                'already_downloaded': all_downloaded,
                'selected': any_to_download,
            })

        self.write({
            'state': 'results',
            'total_isbns_scanned': len(isbns),
        })

        _logger.info(f"ISBN scan complete: {len(isbns)} scanned, {len(isbn_matches)} matched")

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        """Download selected files via the registry's existing download mechanism."""
        self.ensure_one()

        selected = self.result_ids.filtered('selected')
        if not selected:
            raise UserError(_('No ISBNs selected for download.'))

        # Collect all registry record IDs
        registry_ids = []
        for result in selected:
            if result.registry_ids_str:
                for rid in result.registry_ids_str.split(','):
                    if rid.strip():
                        registry_ids.append(int(rid.strip()))

        if not registry_ids:
            raise UserError(_('No files to download.'))

        # Get registry records that aren't downloaded yet
        Registry = self.env['gdrive.file.registry']
        files_to_download = Registry.browse(registry_ids).filtered(lambda f: not f.is_downloaded)

        if not files_to_download:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Nothing to Download'),
                    'message': _('All selected files are already downloaded.'),
                    'type': 'info',
                    'sticky': False,
                }
            }

        _logger.info(f"Starting download of {len(files_to_download)} files from registry")

        # Use the registry's existing download method
        downloaded = 0
        failed = 0

        for file_rec in files_to_download:
            try:
                file_rec.action_download_file()
                downloaded += 1
                _logger.info(f"Downloaded ({downloaded}/{len(files_to_download)}): {file_rec.name}")

                if downloaded % 10 == 0:
                    self.env.cr.commit()

            except Exception as e:
                failed += 1
                _logger.error(f"Failed to download {file_rec.name}: {e}")

        self.env.cr.commit()

        _logger.info(f"ISBN download complete: {downloaded} downloaded, {failed} failed")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('ISBN Download Complete'),
                'message': _('Downloaded: %d files\nFailed: %d files') % (downloaded, failed),
                'type': 'success' if failed == 0 else 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    def action_select_all(self):
        """Select all results that have files to download."""
        self.result_ids.filtered(
            lambda r: not r.already_downloaded
        ).write({'selected': True})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_deselect_all(self):
        """Deselect all results."""
        self.result_ids.write({'selected': False})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ISBNLookupResult(models.TransientModel):
    _name = 'gdrive.isbn.lookup.result'
    _description = 'ISBN Lookup Result'
    _order = 'isbn'

    wizard_id = fields.Many2one('gdrive.isbn.lookup.wizard', ondelete='cascade')
    isbn = fields.Char('ISBN', readonly=True)
    selected = fields.Boolean('Download', default=True)
    file_count = fields.Integer('# Files', readonly=True)
    file_names = fields.Char('Files', readonly=True)
    registry_ids_str = fields.Char('Registry IDs', readonly=True)
    already_downloaded = fields.Boolean('Already Downloaded', readonly=True)