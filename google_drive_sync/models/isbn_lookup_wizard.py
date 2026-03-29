# -*- coding: utf-8 -*-
import base64
import csv
import io
import logging
import time

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

    # Summary fields
    total_isbns_scanned = fields.Integer('Total ISBNs Scanned', readonly=True)
    total_matched = fields.Integer('ISBNs with Files', compute='_compute_stats', store=False)
    total_images = fields.Integer('Total Images Found', compute='_compute_stats', store=False)
    total_texts = fields.Integer('Total Texts Found', compute='_compute_stats', store=False)
    total_not_found = fields.Integer('ISBNs Not Found', compute='_compute_stats', store=False)

    @api.depends('result_ids', 'result_ids.image_count', 'result_ids.text_count', 'total_isbns_scanned')
    def _compute_stats(self):
        for rec in self:
            rec.total_matched = len(rec.result_ids)
            rec.total_images = sum(rec.result_ids.mapped('image_count'))
            rec.total_texts = sum(rec.result_ids.mapped('text_count'))
            rec.total_not_found = rec.total_isbns_scanned - len(rec.result_ids)

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

    def _drive_api_call_with_retry(self, api_call, max_retries=3):
        """Execute a Drive API call with retry logic for transient errors."""
        for attempt in range(max_retries):
            try:
                return api_call.execute()
            except Exception as e:
                error_str = str(e)
                if attempt < max_retries - 1 and (
                    'token' in error_str.lower()
                    or 'timeout' in error_str.lower()
                    or 'connection' in error_str.lower()
                    or '503' in error_str
                    or '429' in error_str
                ):
                    wait_time = (attempt + 1) * 5  # 5s, 10s, 15s
                    _logger.warning(f"Drive API call failed (attempt {attempt + 1}/{max_retries}), "
                                    f"retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise
        return None

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
                    request = service.files().list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, size)",
                        pageSize=1000,
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        corpora='allDrives',
                        pageToken=page_token,
                    )
                    resp = self._drive_api_call_with_retry(request)

                    if not resp:
                        _logger.error(f"Drive API returned empty response for folder {folder_id}")
                        break

                except Exception as e:
                    _logger.error(f"Drive API error scanning folder {folder_id} "
                                  f"(after retries): {e}")
                    raise UserError(_(
                        'Failed to scan Google Drive folder.\n'
                        'Error: %s\n\n'
                        'Please check the service account configuration and try again.'
                    ) % str(e))

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
        """Match ISBNs to Drive files locally using set-based lookup.
        
        For each file, extracts the leading digits from the filename and checks
        against the ISBN set. Tries ISBN-13 (first 13 digits) before ISBN-10
        (first 10 digits) so longer matches take priority.
        
        This is O(n) where n = number of files, instead of O(n*m) with m = ISBNs.
        """
        isbn_set = set(isbns)
        results = {}
        matched = 0

        for f in drive_files:
            fname = f['name']
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            name_without_ext = fname.rsplit('.', 1)[0] if '.' in fname else fname

            if ext not in ('jpg', 'jpeg', 'txt'):
                continue

            # Extract leading digits from filename
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
                if matched_isbn not in results:
                    results[matched_isbn] = {'images': [], 'texts': []}
                    matched += 1
                if ext in ('jpg', 'jpeg'):
                    results[matched_isbn]['images'].append(f)
                elif ext == 'txt':
                    results[matched_isbn]['texts'].append(f)

        _logger.info(f"Matching complete: {matched} ISBNs matched across {len(drive_files)} files")
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

        # --- Create result records (only for matches) ---
        ResultModel = self.env['gdrive.isbn.lookup.result']
        self.result_ids.unlink()

        created = 0
        for isbn in isbns:
            if isbn not in matches:
                continue

            match = matches[isbn]
            image_files = match['images']
            text_files = match['texts']

            if not image_files and not text_files:
                continue

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
                'selected': True,
            })
            created += 1

        self.write({
            'state': 'results',
            'total_isbns_scanned': len(isbns),
        })

        _logger.info(f"ISBN scan complete: {len(isbns)} ISBNs scanned, "
                     f"{created} with matches, "
                     f"{len(isbns) - created} not found on Drive")

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
                meta_request = service.files().get(
                    fileId=file_id,
                    fields="name, mimeType, size",
                    supportsAllDrives=True,
                )
                file_meta = self._drive_api_call_with_retry(meta_request)

                file_name = file_meta['name']
                mime_type = file_meta.get('mimeType', 'application/octet-stream')

                # Download content
                dl_request = service.files().get_media(fileId=file_id)
                file_content = self._drive_api_call_with_retry(dl_request)

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
        """Select all results."""
        self.result_ids.write({'selected': True})
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