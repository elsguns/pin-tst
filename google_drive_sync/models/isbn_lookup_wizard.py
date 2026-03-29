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

    state = fields.Selection([
        ('start', 'Start'),
        ('files', 'Drive Files'),
    ], default='start', string='State')

    file_ids = fields.One2many('gdrive.isbn.lookup.file', 'wizard_id', string='Files')
    total_files = fields.Integer('Total Files', readonly=True)

    def _drive_api_call_with_retry(self, api_call, max_retries=3):
        """Execute a Drive API call with retry logic for transient errors."""
        for attempt in range(max_retries):
            try:
                return api_call.execute()
            except Exception as e:
                error_str = str(e).lower()
                if attempt < max_retries - 1 and (
                    'token' in error_str
                    or 'timeout' in error_str
                    or 'connection' in error_str
                    or '503' in str(e)
                    or '429' in str(e)
                ):
                    wait_time = (attempt + 1) * 5
                    _logger.warning(f"Drive API call failed (attempt {attempt + 1}/{max_retries}), "
                                    f"retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    raise
        return None

    def action_fetch_files(self):
        """Fetch all jpg/txt files from product content folders."""
        self.ensure_one()

        # --- Get product content folders ---
        product_folders = self.env['gdrive.folder.selection'].search([
            ('selected', '=', True),
            ('download_product_content', '=', True),
        ])
        if not product_folders:
            raise UserError(_('No folders are configured for Product Images & Descriptions. '
                              'Please enable "Product Images & Descriptions" on at least one folder.'))

        folder_ids = product_folders.mapped('folder_id')
        _logger.info(f"Fetching files from {len(folder_ids)} product content folder(s)")

        # --- Get Drive service ---
        ICPSudo = self.env['ir.config_parameter'].sudo()
        service_json = ICPSudo.get_param('gdrive.service_account_json', '')
        if not service_json:
            raise UserError(_('Google Drive service account not configured.'))

        service = self.env['gdrive.file.registry']._get_drive_service(service_json)

        # --- Fetch all jpg/txt files ---
        all_files = []
        for folder_id in folder_ids:
            query = (
                f"'{folder_id}' in parents"
                f" and mimeType != 'application/vnd.google-apps.folder'"
                f" and (mimeType = 'image/jpeg' or mimeType = 'text/plain')"
            )
            page_token = None
            folder_count = 0

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
                        _logger.error(f"Empty response for folder {folder_id}")
                        break

                except Exception as e:
                    _logger.error(f"Drive API error for folder {folder_id}: {e}")
                    raise UserError(_('Failed to fetch files from Google Drive: %s') % str(e))

                files = resp.get('files', [])
                for f in files:
                    f['folder_id'] = folder_id
                all_files.extend(files)
                folder_count += len(files)

                page_token = resp.get('nextPageToken')
                if not page_token:
                    break

                _logger.info(f"Folder {folder_id}: fetched {folder_count} files so far...")

            _logger.info(f"Folder {folder_id}: {folder_count} jpg/txt files total")

        _logger.info(f"Total files fetched: {len(all_files)}")

        # --- Store in transient model ---
        self.file_ids.unlink()
        FileModel = self.env['gdrive.isbn.lookup.file']

        for f in all_files:
            ext = f['name'].rsplit('.', 1)[-1].lower() if '.' in f['name'] else ''
            FileModel.create({
                'wizard_id': self.id,
                'drive_file_id': f['id'],
                'name': f['name'],
                'mime_type': f.get('mimeType', ''),
                'size': int(f.get('size', 0)),
                'file_type': 'image' if ext in ('jpg', 'jpeg') else 'text',
            })

        self.write({
            'state': 'files',
            'total_files': len(all_files),
        })

        _logger.info(f"Stored {len(all_files)} file records")

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class ISBNLookupFile(models.TransientModel):
    _name = 'gdrive.isbn.lookup.file'
    _description = 'Drive File List'
    _order = 'name'

    wizard_id = fields.Many2one('gdrive.isbn.lookup.wizard', ondelete='cascade')
    drive_file_id = fields.Char('Drive File ID', readonly=True)
    name = fields.Char('Filename', readonly=True)
    mime_type = fields.Char('MIME Type', readonly=True)
    size = fields.Integer('Size (bytes)', readonly=True)
    file_type = fields.Selection([
        ('image', 'Image'),
        ('text', 'Text'),
    ], string='Type', readonly=True)