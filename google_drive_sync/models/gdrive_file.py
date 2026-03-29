import json
import logging
import os
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from google.oauth2 import service_account
from googleapiclient.discovery import build
import base64

_logger = logging.getLogger(__name__)

class GDriveFileRegistry(models.Model):
    """Model to store discovered Google Drive files"""
    _name = 'gdrive.file.registry'
    _description = 'Google Drive File Registry'
    _order = 'folder_path, name'
    _rec_name = 'name'
    
    # File information
    file_id = fields.Char('Google Drive File ID', required=True, index=True)
    name = fields.Char('File Name', required=True)
    mime_type = fields.Char('MIME Type')
    size = fields.Integer('Size (bytes)')
    modified_time = fields.Datetime('Modified Time')
    created_time = fields.Datetime('Created Time')
    
    # Folder information
    folder_id = fields.Char('Folder ID', required=True)
    folder_name = fields.Char('Folder Name')
    folder_path = fields.Char('Folder Path')
    
    # Download status
    is_downloaded = fields.Boolean('Downloaded', default=False)
    download_date = fields.Datetime('Download Date')
    attachment_id = fields.Many2one('ir.attachment', string='Attachment', ondelete='set null')
    
    # Computed fields
    size_display = fields.Char('Size', compute='_compute_size_display', store=False)
    can_download = fields.Boolean('Can Download', compute='_compute_can_download', store=False)
    
    _sql_constraints = [
        ('file_id_unique', 'UNIQUE(file_id)', 'File ID must be unique!')
    ]
    
    @api.depends('size')
    def _compute_size_display(self):
        """Compute human-readable file size"""
        for record in self:
            size = record.size or 0
            if size < 1024:
                record.size_display = f"{size} B"
            elif size < 1024 * 1024:
                record.size_display = f"{size / 1024:.1f} KB"
            elif size < 1024 * 1024 * 1024:
                record.size_display = f"{size / (1024 * 1024):.1f} MB"
            else:
                record.size_display = f"{size / (1024 * 1024 * 1024):.2f} GB"
    
    @api.depends('is_downloaded', 'size')
    def _compute_can_download(self):
        """Check if file can be downloaded"""
        for record in self:
            # Skip files larger than 100MB
            record.can_download = not record.is_downloaded and (record.size or 0) < (100 * 1024 * 1024)
    
    def action_download_file(self):
        """Download individual file to attachments"""
        self.ensure_one()
        
        if self.is_downloaded and self.attachment_id:
            # File already downloaded, show notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Already Downloaded'),
                    'message': _('File "%s" is already in attachments') % self.name,
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Get service
        ICPSudo = self.env['ir.config_parameter'].sudo()
        SERVICE_ACCOUNT_JSON = ICPSudo.get_param('gdrive.service_account_json', '')
        
        if not SERVICE_ACCOUNT_JSON:
            raise UserError(_('Google Drive service account not configured.'))
        
        service = self._get_drive_service(SERVICE_ACCOUNT_JSON)
        
        # Download the file
        try:
            _logger.info(f"Downloading file: {self.name}")
            
            file_name = self.name
            mime_type = self.mime_type
            
            # Handle Google Workspace files
            if mime_type == 'application/vnd.google-apps.document':
                # Export Google Doc as PDF
                request = service.files().export_media(fileId=self.file_id, mimeType='application/pdf')
                file_name = file_name + '.pdf' if not file_name.endswith('.pdf') else file_name
                mime_type = 'application/pdf'
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                # Export Google Sheets as Excel
                request = service.files().export_media(fileId=self.file_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                file_name = file_name + '.xlsx' if not file_name.endswith('.xlsx') else file_name
                mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            elif mime_type == 'application/vnd.google-apps.presentation':
                # Export Google Slides as PowerPoint
                request = service.files().export_media(fileId=self.file_id, 
                    mimeType='application/vnd.openxmlformats-officedocument.presentationml.presentation')
                file_name = file_name + '.pptx' if not file_name.endswith('.pptx') else file_name
                mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            else:
                # Download regular file
                request = service.files().get_media(fileId=self.file_id)
            
            file_content = request.execute()
            
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')
            file_content_base64 = base64.b64encode(file_content).decode('utf-8')
            
            # Create attachment
            attachment_vals = {
                'name': file_name,
                'type': 'binary',
                'datas': file_content_base64,
                'mimetype': mime_type,
                'description': f'Downloaded from Google Drive: {self.folder_path}',
            }
            attachment = self.env['ir.attachment'].create(attachment_vals)
            
            # Update registry record
            self.write({
                'is_downloaded': True,
                'download_date': fields.Datetime.now(),
                'attachment_id': attachment.id,
            })
            
            _logger.info(f"Successfully downloaded: {file_name}")
            
            # Show notification of successful download
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Download Complete'),
                    'message': _('File "%s" has been saved to attachments') % file_name,
                    'type': 'success',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'reload'},
                }
            }
            
        except Exception as e:
            _logger.error(f"Error downloading file {self.name}: {str(e)}")
            raise UserError(_('Failed to download file: %s') % str(e))
    
    def _get_drive_service(self, service_account_json):
        """Get authenticated Google Drive service"""
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        
        credentials_info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info, scopes=SCOPES)
        
        return build('drive', 'v3', credentials=credentials)
    
    @api.model
    def action_download_selected(self):
        """Mass download action for selected files"""
        active_ids = self.env.context.get('active_ids', [])
        if not active_ids:
            raise UserError(_('No files selected.'))
        
        files = self.browse(active_ids)
        downloaded = 0
        failed = 0
        
        for file_rec in files:
            if file_rec.can_download:
                try:
                    file_rec.action_download_file()
                    downloaded += 1
                except Exception as e:
                    _logger.error(f"Failed to download {file_rec.name}: {str(e)}")
                    failed += 1
        
        message = _('Download complete!\n')
        if downloaded:
            message += _('Successfully downloaded: %d files\n') % downloaded
        if failed:
            message += _('Failed: %d files') % failed
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mass Download Complete'),
                'message': message,
                'type': 'success' if failed == 0 else 'warning',
                'sticky': False,
            }
        }

    @api.model
    def action_scan_google_drive_files(self):
        """Trigger Google Drive sync from tree header button"""
        return self.env['gdrive.file'].sync_google_drive_files()

    @api.model
    def action_purge_registry(self):
        """Delete all records from the file registry"""
        # Delete all records in this model
        all_records = self.search([])
        all_records.unlink()
        
        # Return a notification action
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Registry Purged'),
                'message': _('All file registry records have been deleted.'),
                'type': 'warning',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'reload'},
            }
        }

    @api.model
    def auto_download_product_content(self):
        """Automatically download product images (JPG) and descriptions (TXT) from configured folders"""
        # Get batch size from system parameters
        ICPSudo = self.env['ir.config_parameter'].sudo()
        batch_size = int(ICPSudo.get_param('gdrive.auto_download_batch_size', '10'))
        
        _logger.info(f"Starting auto-download for product content (JPG/TXT) - batch size: {batch_size}")
        
        # Get service account JSON
        SERVICE_ACCOUNT_JSON = ICPSudo.get_param('gdrive.service_account_json', '')
        
        if not SERVICE_ACCOUNT_JSON:
            _logger.warning('Google Drive service account not configured. Skipping auto-download.')
            return
        
        # Find folders with product content download enabled
        FolderSelection = self.env['gdrive.folder.selection']
        product_folders = FolderSelection.search([
            ('selected', '=', True),
            ('download_product_content', '=', True)
        ])
        
        if not product_folders:
            _logger.info('No folders configured for product content auto-download.')
            return
        
        folder_ids = product_folders.mapped('folder_id')
        _logger.info(f"Found {len(product_folders)} folders enabled for product content download")
        
        # MIME types for product content: JPG images and TXT descriptions
        mime_types = ['image/jpeg', 'image/jpg', 'text/plain']
        
        # Build domain to find files
        domain = [
            ('is_downloaded', '=', False),
            ('size', '<=', 100 * 1024 * 1024),  # Max 100MB
            ('folder_id', 'in', folder_ids),
            ('mime_type', 'in', mime_types)
        ]
        
        files_to_download = self.search(domain, order='modified_time asc', limit=batch_size)
        
        if not files_to_download:
            _logger.info('No product content files (JPG/TXT) to download.')
            return
        
        _logger.info(f"Found {len(files_to_download)} product content files to download")
        
        # Get Google Drive service
        service = self._get_drive_service(SERVICE_ACCOUNT_JSON)
        
        downloaded = 0
        failed = 0
        
        for file_rec in files_to_download:
            try:
                _logger.info(f"Auto-downloading: {file_rec.name}")
                
                file_name = file_rec.name
                mime_type = file_rec.mime_type
                
                # Download regular file (JPG and TXT don't need special handling)
                request = service.files().get_media(fileId=file_rec.file_id)
                
                file_content = request.execute()
                
                if isinstance(file_content, str):
                    file_content = file_content.encode('utf-8')
                file_content_base64 = base64.b64encode(file_content).decode('utf-8')
                
                # Create attachment
                attachment_vals = {
                    'name': file_name,
                    'type': 'binary',
                    'datas': file_content_base64,
                    'mimetype': mime_type,
                    'description': f'Product content from Google Drive: {file_rec.folder_path}',
                }
                attachment = self.env['ir.attachment'].create(attachment_vals)
                
                # Update registry record
                file_rec.write({
                    'is_downloaded': True,
                    'download_date': fields.Datetime.now(),
                    'attachment_id': attachment.id,
                })
                
                downloaded += 1
                _logger.info(f"Successfully auto-downloaded: {file_name}")
                
                # Commit after each file to save progress
                self.env.cr.commit()
                
            except Exception as e:
                failed += 1
                _logger.error(f"Failed to auto-download {file_rec.name}: {str(e)}")
                # Continue with next file
        
        _logger.info(f"Product content auto-download complete: {downloaded} downloaded, {failed} failed")

    @api.model
    def auto_download_import_data(self):
        """Automatically download import data files (CSV/XLS/XLSX/TXT) from configured folders"""
        # Get batch size from system parameters
        ICPSudo = self.env['ir.config_parameter'].sudo()
        batch_size = int(ICPSudo.get_param('gdrive.auto_download_batch_size', '10'))
        
        _logger.info(f"Starting auto-download for import data (CSV/XLS/XLSX/TXT) - batch size: {batch_size}")
        
        # Get service account JSON
        SERVICE_ACCOUNT_JSON = ICPSudo.get_param('gdrive.service_account_json', '')
        
        if not SERVICE_ACCOUNT_JSON:
            _logger.warning('Google Drive service account not configured. Skipping auto-download.')
            return
        
        # Find folders with import data download enabled
        FolderSelection = self.env['gdrive.folder.selection']
        import_folders = FolderSelection.search([
            ('selected', '=', True),
            ('download_import_data', '=', True)
        ])
        
        if not import_folders:
            _logger.info('No folders configured for import data auto-download.')
            return
        
        folder_ids = import_folders.mapped('folder_id')
        _logger.info(f"Found {len(import_folders)} folders enabled for import data download")
        
        # MIME types for import data: spreadsheets and text files
        mime_types = [
            'text/plain',                                                         # TXT
            'text/csv',                                                          # CSV
            'application/vnd.ms-excel',                                          # XLS
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', # XLSX
            'application/vnd.oasis.opendocument.spreadsheet',                    # ODS
        ]
        
        # Build domain to find files
        domain = [
            ('is_downloaded', '=', False),
            ('size', '<=', 100 * 1024 * 1024),  # Max 100MB
            ('folder_id', 'in', folder_ids),
            ('mime_type', 'in', mime_types)
        ]
        
        files_to_download = self.search(domain, order='modified_time asc', limit=batch_size)
        
        if not files_to_download:
            _logger.info('No import data files to download.')
            return
        
        _logger.info(f"Found {len(files_to_download)} import data files to download")
        
        # Get Google Drive service
        service = self._get_drive_service(SERVICE_ACCOUNT_JSON)
        
        downloaded = 0
        failed = 0
        
        for file_rec in files_to_download:
            try:
                _logger.info(f"Auto-downloading: {file_rec.name}")
                
                file_name = file_rec.name
                mime_type = file_rec.mime_type
                
                # Extract last folder name from path
                # "Drive/DATA IMPORT ODOO/Taschen" -> "Taschen"
                folder_name = file_rec.folder_path.split('/')[-1] if file_rec.folder_path else None
                partner = None
                
                if folder_name:
                    partner = self.env['res.partner'].search([
                        ('name', '=', folder_name)
                    ], limit=1)
                    
                    if partner:
                        _logger.info(f"Matched folder '{folder_name}' to partner: {partner.name} (ID: {partner.id})")
                    else:
                        _logger.warning(f"No partner found matching folder name: {folder_name}")
                
                # Handle Google Workspace spreadsheets
                if mime_type == 'application/vnd.google-apps.spreadsheet':
                    # Export Google Sheets as Excel
                    request = service.files().export_media(fileId=file_rec.file_id, 
                        mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    file_name = file_name + '.xlsx' if not file_name.endswith('.xlsx') else file_name
                    mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                else:
                    # Download regular file
                    request = service.files().get_media(fileId=file_rec.file_id)
                
                file_content = request.execute()
                
                if isinstance(file_content, str):
                    file_content = file_content.encode('utf-8')
                file_content_base64 = base64.b64encode(file_content).decode('utf-8')
                
                # Create attachment - LINK TO PARTNER
                attachment_vals = {
                    'name': file_name,
                    'type': 'binary',
                    'datas': file_content_base64,
                    'mimetype': mime_type,
                    'description': f'Import data from Google Drive: {file_rec.folder_path}',
                }
                
                # Add partner link if found
                if partner:
                    attachment_vals['res_model'] = 'res.partner'
                    attachment_vals['res_id'] = partner.id
                
                attachment = self.env['ir.attachment'].create(attachment_vals)
                
                # Update registry record
                file_rec.write({
                    'is_downloaded': True,
                    'download_date': fields.Datetime.now(),
                    'attachment_id': attachment.id,
                })
                
                downloaded += 1
                _logger.info(f"Successfully auto-downloaded: {file_name}")
                
                # Commit after each file to save progress
                self.env.cr.commit()
                
            except Exception as e:
                failed += 1
                _logger.error(f"Failed to auto-download {file_rec.name}: {str(e)}")
                # Continue with next file
        
        _logger.info(f"Import data auto-download complete: {downloaded} downloaded, {failed} failed")

    @api.model
    def auto_download_images_and_text(self):
        """Convenience wrapper: calls auto_download_product_content() for backward compatibility"""
        return self.auto_download_product_content()

class GDriveFile(models.Model):
    _name = 'gdrive.file'
    _description = 'Google Drive Files Sync'
    
    # This model is just a placeholder for the sync method
    name = fields.Char('Placeholder')
    
    @api.model
    def action_sync_google_drive(self):
        """Action method that can be called from menu"""
        return self.sync_google_drive_files()
    
    @api.model
    def sync_google_drive_files(self):
        """Main sync method - scans all files found in time period and stores them in registry"""
        
        # Get settings - EXACTLY like the original
        ICPSudo = self.env['ir.config_parameter'].sudo()
        SERVICE_ACCOUNT_JSON = ICPSudo.get_param('gdrive.service_account_json', '')
        TIME_PERIOD = ICPSudo.get_param('gdrive.sync_time_period', '1')
        
        if not SERVICE_ACCOUNT_JSON:
            raise UserError(_('Google Drive service account not configured.'))
        
        # Get selected folders from the permanent model
        selected_folders = self.env['gdrive.folder.selection'].search([('selected', '=', True)])
        
        if not selected_folders:
            raise UserError(_('No folders selected for sync. Please go to Settings and select folders.'))
        
        # Calculate date threshold based on time period
        if TIME_PERIOD == 'all':
            date_threshold = None
            _logger.info(f"Starting sync for {len(selected_folders)} folders, syncing ALL files")
        else:
            days_back = int(TIME_PERIOD)
            date_threshold = (datetime.now() - timedelta(days=days_back)).isoformat() + 'Z'
            _logger.info(f"Starting sync for {len(selected_folders)} folders, looking back {days_back} days")
            _logger.info(f"Date threshold: {date_threshold}")
        
        # Get Google Drive service
        service = self._get_drive_service(SERVICE_ACCOUNT_JSON)
        
        # Get file registry model
        FileRegistry = self.env['gdrive.file.registry']
        
        # Process each selected folder
        total_found = 0
        total_new = 0
        total_updated = 0
        
        for folder_record in selected_folders:
            folder_id = folder_record.folder_id
            folder_name = folder_record.folder_name
            folder_path = folder_record.folder_path
            
            _logger.info(f"Scanning folder: {folder_path} (ID: {folder_id})")
            
            # Query for files - with or without date filter
            if date_threshold is None:
                # Sync all files regardless of modification date
                query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder'"
            else:
                # Sync files where EITHER modifiedTime OR createdTime is after threshold
                query = f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder' and (modifiedTime > '{date_threshold}' or createdTime > '{date_threshold}')"
            
            page_token = None
            folder_file_count = 0
            
            while True:
                try:
                    _logger.info(f"Fetching files from folder {folder_name}, page token: {page_token}")
                    
                    # EXACTLY the same API call as the original
                    results = service.files().list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, createdTime)",
                        pageSize=100,  # Same as original
                        includeItemsFromAllDrives=True,
                        supportsAllDrives=True,
                        corpora='allDrives',
                        pageToken=page_token
                    ).execute()
                    
                    files = results.get('files', [])
                    _logger.info(f"Found {len(files)} files in this batch")
                    folder_file_count += len(files)
                    total_found += len(files)
                    
                    for file_data in files:
                        file_id = file_data['id']
                        file_size = int(file_data.get('size', 0))
                        file_name = file_data.get('name', 'Unknown')
                        
                        # Skip very large files (>100MB) - like the original
                        if file_size > 100 * 1024 * 1024:
                            _logger.warning(f"Skipping large file {file_name}: {file_size / (1024*1024):.2f} MB")
                            continue
                        
                        # Check if file already exists in registry
                        existing_file = FileRegistry.search([('file_id', '=', file_id)], limit=1)
                        
                        # Parse modified time - Odoo expects naive datetime (no timezone)
                        modified_time_str = file_data.get('modifiedTime', '')
                        modified_time = False
                        if modified_time_str:
                            try:
                                # Parse the datetime and convert to naive (remove timezone info)
                                dt_with_tz = datetime.fromisoformat(modified_time_str.replace('Z', '+00:00'))
                                # Convert to naive datetime by removing timezone info
                                modified_time = dt_with_tz.replace(tzinfo=None)
                            except Exception as e:
                                _logger.warning(f"Could not parse modified time for {file_name}: {e}")
                                pass
                        
                        # Parse created time - Odoo expects naive datetime (no timezone)
                        created_time_str = file_data.get('createdTime', '')
                        created_time = False
                        if created_time_str:
                            try:
                                # Parse the datetime and convert to naive (remove timezone info)
                                dt_with_tz = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                                # Convert to naive datetime by removing timezone info
                                created_time = dt_with_tz.replace(tzinfo=None)
                            except Exception as e:
                                _logger.warning(f"Could not parse created time for {file_name}: {e}")
                                pass
                        
                        file_vals = {
                            'file_id': file_id,
                            'name': file_name,
                            'mime_type': file_data.get('mimeType', ''),
                            'size': file_size,
                            'modified_time': modified_time,
                            'created_time': created_time,
                            'folder_id': folder_id,
                            'folder_name': folder_name,
                            'folder_path': folder_path,
                        }
                        
                        if existing_file:
                            # Check if file was modified after download - if so, mark for re-download
                            update_vals = {
                                'name': file_name,
                                'mime_type': file_data.get('mimeType', ''),
                                'size': file_size,
                                'modified_time': modified_time,
                                'created_time': created_time,
                                'folder_name': folder_name,
                                'folder_path': folder_path,
                            }
                            
                            # If file was downloaded and then modified, reset download status
                            if existing_file.is_downloaded and existing_file.download_date and modified_time:
                                if modified_time > existing_file.download_date:
                                    update_vals['is_downloaded'] = False
                                    update_vals['download_date'] = False
                                    update_vals['attachment_id'] = False
                                    _logger.info(f"File modified after download, marking for re-download: {file_name}")
                            
                            existing_file.write(update_vals)
                            total_updated += 1
                            _logger.info(f"Updated existing file: {file_name}")
                        else:
                            # Create new registry entry instead of downloading
                            FileRegistry.create(file_vals)
                            total_new += 1
                            _logger.info(f"Added to registry: {file_name}")
                        
                        # Commit every 10 files like the original
                        if (total_new + total_updated) % 10 == 0:
                            self.env.cr.commit()
                            _logger.info(f"Committed {total_new + total_updated} records to database")
                    
                    page_token = results.get('nextPageToken')
                    if not page_token:
                        break
                        
                except Exception as e:
                    _logger.error(f"Error processing folder {folder_name}: {str(e)}")
                    _logger.error(f"Error details: {repr(e)}")
                    break
            
            _logger.info(f"Finished folder {folder_name}: found {folder_file_count} files")
            
            # Update last sync time for this folder
            folder_record.last_sync = fields.Datetime.now()
            self.env.cr.commit()  # Commit folder update
        
        # Final commit
        self.env.cr.commit()
        
        _logger.info(f"Sync complete: Found {total_found} files, added {total_new} new, updated {total_updated} existing")
        
        message = _(f'Scan Complete\nFound: {total_found} files\nNew files: {total_new}\nUpdated: {total_updated}')
        
        # Return action to show the file registry
        return {
            'type': 'ir.actions.act_window',
            'name': _('Google Drive Files'),
            'res_model': 'gdrive.file.registry',
            'view_mode': 'tree,form',
            'target': 'current',
            'context': {},
        }
    
    def _get_drive_service(self, service_account_json):
        """Get authenticated Google Drive service"""
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        
        credentials_info = json.loads(service_account_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info, scopes=SCOPES)
        
        return build('drive', 'v3', credentials=credentials)