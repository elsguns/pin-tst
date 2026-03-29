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
    csv_file = fields.Binary('CSV File', required=True)
    csv_filename = fields.Char('Filename')

    # Step 2: Results
    state = fields.Selection([
        ('upload', 'Upload'),
        ('results', 'Results'),
    ], default='upload', string='State')

    result_ids = fields.One2many('gdrive.isbn.lookup.result', 'wizard_id', string='Results')

    # Stats (computed)
    total_isbns = fields.Integer('Total ISBNs', compute='_compute_stats', store=False)
    found_images = fields.Integer('Images Found', compute='_compute_stats', store=False)
    found_texts = fields.Integer('Texts Found', compute='_compute_stats', store=False)

    @api.depends('result_ids', 'result_ids.image_found', 'result_ids.text_found')
    def _compute_stats(self):
        for rec in self:
            rec.total_isbns = len(rec.result_ids)
            rec.found_images = len(rec.result_ids.filtered('image_found'))
            rec.found_texts = len(rec.result_ids.filtered('text_found'))

    def _parse_isbns(self):
        """Parse ISBNs from the uploaded CSV file."""
        raw = base64.b64decode(self.csv_file)
        # Try utf-8-sig first (handles BOM), fall back to utf-8 then latin-1
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        # Try to detect delimiter
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

        # Remove duplicates, preserve order
        seen = set()
        unique_isbns = []
        for isbn in isbns:
            if isbn not in seen:
                seen.add(isbn)
                unique_isbns.append(isbn)

        return unique_isbns

    def _get_all_files_from_folders(self, service, folder_ids):
        """Query each folder once and return all jpg/txt files as a flat list.
        
        This is much faster than querying per ISBN: one paginated query per folder
        instead of one query per ISBN per folder.
        """
        all_files = []

        for folder_id in folder_ids:
            # Query for jpg and txt files only
            query = (
                f"'{folder_id}' in parents"
                f" and mimeType != 'application/vnd.google-apps.folder'"
                f" and (mimeType = 'image/jpeg' or mimeType = 'text/plain')"
            )

            page_token = None
            folder_file_count = 0

            while True:
                try:
                    resp = service.files().list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, size)",
                        pageSize=1000,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        corpora='allDrives',
                        pageToken=page_token,
                    ).execute()
                except Exception as e:
                    _logger.error(f"Drive API error scanning folder {folder_id}: {e}")
                    break

                files = resp.get('files', [])
                all_files.extend(files)
                folder_file_count += len(files)

                page_token = resp.get('nextPageToken')
                if not page_token:
                    break

            _logger.info(f"Folder {folder_id}: found {folder_file_count} jpg/txt files")

        _logger.info(f"Total files retrieved from Drive: {len(all_files)}")
        return all_files

    def _match_isbns_to_files(self, isbns, drive_files):
        """Match ISBNs to Drive files locally.
        
        Builds a dict keyed by ISBN with lists of matching image/text files.
        A file matches if its name (without extension) starts with the ISBN.
        """
        isbn_set = set(isbns)
        results = {isbn: {'images': [], 'texts': []} for isbn in isbns}

        for f in drive_files:
            fname = f['name']
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            name_without_ext = fname.rsplit('.', 1)[0] if '.' in fname else fname

            # Check which ISBN this file belongs to
            for isbn in isbn_set:
                if name_without_ext.startswith(isbn):
                    if ext in ('jpg', 'jpeg'):
                        results[isbn]['images'].append(f)
                    elif ext == 'txt':
                        results[isbn]['texts'].append(f)
                    break  # A file belongs to one ISBN only

        return results

    def action_scan(self):
        """Parse CSV and scan Google Drive for matching files."""
        self.ensure_one()

        if not self.csv_file:
            raise UserError(_('Please upload a CSV file.'))

        # --- Parse ISBNs ---
        isbns = self._parse_isbns()
        if not isbns:
            raise UserError(_('No valid ISBNs found in the CSV file.'))

        _logger.info(f"Parsed {len(isbns)} unique ISBNs from CSV")

        # --- Get product content folders ---
        product_folders = self.env['gdrive.folder.selection'].search([
            ('selected', '=', True),
            ('download_product_content', '=', True),
        ])
        if not product_folders:
            raise UserError(_('No folders are configured for Product Images & Descriptions. '
                              'Please enable "Product Images & Descriptions" on at least one folder.'))

        folder_ids = product_folders.mapped('folder_id')
        _logger.info(f"Scanning {len(folder_ids)} product content folder(s)")

        # --- Get Drive service ---
        ICPSudo = self.env['ir.config_parameter'].sudo()
        service_json = ICPSudo.get_param('gdrive.service_account_json', '')
        if not service_json:
            raise UserError(_('Google Drive service account not configured.'))

        service = self.env['gdrive.file.registry']._get_drive_service(service_json)

        # --- Fetch ALL jpg/txt files from the folders (folder-first approach) ---
        drive_files = self._get_all_files_from_folders(service, folder_ids)

        # --- Match ISBNs to files locally ---
        matches = self._match_isbns_to_files(isbns, drive_files)

        # --- Create result records ---
        ResultModel = self.env['gdrive.isbn.lookup.result']
        self.result_ids.unlink()

        for isbn in isbns:
            match = matches[isbn]
            image_files = match['images']
            text_files = match['texts']

            ResultModel.create({
                'wizard_id': self.id,
                'isbn': isbn,
                'image_found': bool(image_files),
                'image_file_ids': ','.join(f['id'] for f in image_files),
                'image_file_names': ', '.join(f['name'] for f in image_files),
                'image_count': len(image_files),
                'text_found': bool(text_files),
                'text_file_ids': ','.join(f['id'] for f in text_files),
                'text_file_names': ', '.join(f['name'] for f in text_files),
                'text_count': len(text_files),
                'selected': bool(image_files) or bool(text_files),
            })

        self.state = 'results'

        found_img = sum(1 for isbn in isbns if matches[isbn]['images'])
        found_txt = sum(1 for isbn in isbns if matches[isbn]['texts'])
        _logger.info(f"ISBN scan complete: {len(isbns)} ISBNs, "
                     f"{found_img} with images, {found_txt} with texts")

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_download(self):
        """Download all selected files."""
        self.ensure_one()

        selected = self.result_ids.filtered('selected')
        if not selected:
            raise UserError(_('No ISBNs selected for download.'))

        # Collect all file IDs to download
        file_ids_to_download = []
        for result in selected:
            if result.image_file_ids:
                for fid in result.image_file_ids.split(','):
                    if fid.strip():
                        file_ids_to_download.append(fid.strip())
            if result.text_file_ids:
                for fid in result.text_file_ids.split(','):
                    if fid.strip():
                        file_ids_to_download.append(fid.strip())

        if not file_ids_to_download:
            raise UserError(_('No files to download.'))

        _logger.info(f"Starting download of {len(file_ids_to_download)} files")

        # Get Drive service
        ICPSudo = self.env['ir.config_parameter'].sudo()
        service_json = ICPSudo.get_param('gdrive.service_account_json', '')
        service = self.env['gdrive.file.registry']._get_drive_service(service_json)

        downloaded = 0
        failed = 0

        for file_id in file_ids_to_download:
            try:
                # Get file metadata
                file_meta = service.files().get(
                    fileId=file_id,
                    fields="name, mimeType, size",
                    supportsAllDrives=True,
                ).execute()

                file_name = file_meta['name']
                mime_type = file_meta.get('mimeType', 'application/octet-stream')

                # Download content
                request = service.files().get_media(fileId=file_id)
                file_content = request.execute()

                if isinstance(file_content, str):
                    file_content = file_content.encode('utf-8')

                file_content_base64 = base64.b64encode(file_content).decode('utf-8')

                # Create attachment
                self.env['ir.attachment'].create({
                    'name': file_name,
                    'type': 'binary',
                    'datas': file_content_base64,
                    'mimetype': mime_type,
                    'description': 'ISBN lookup download from Google Drive',
                })

                downloaded += 1
                _logger.info(f"Downloaded ({downloaded}/{len(file_ids_to_download)}): {file_name}")

                # Commit every 10 files to save progress
                if downloaded % 10 == 0:
                    self.env.cr.commit()

            except Exception as e:
                failed += 1
                _logger.error(f"Failed to download file {file_id}: {e}")

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
        """Select all results that have files."""
        self.result_ids.filtered(
            lambda r: r.image_found or r.text_found
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
    selected = fields.Boolean('Download', default=False)

    # Image info
    image_found = fields.Boolean('Image', readonly=True)
    image_file_ids = fields.Char('Image File IDs', readonly=True)
    image_file_names = fields.Char('Image Files', readonly=True)
    image_count = fields.Integer('# Images', readonly=True)

    # Text info
    text_found = fields.Boolean('Text', readonly=True)
    text_file_ids = fields.Char('Text File IDs', readonly=True)
    text_file_names = fields.Char('Text Files', readonly=True)
    text_count = fields.Integer('# Texts', readonly=True)