from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)

class GDriveFolderSelection(models.Model):
    """Permanent model to store folder selections"""
    _name = 'gdrive.folder.selection'
    _description = 'Google Drive Folder Selection'
    _order = 'folder_path'
    
    folder_id = fields.Char('Folder ID', required=True, index=True)
    folder_name = fields.Char('Name', required=True)
    folder_path = fields.Char('Path', required=True)
    selected = fields.Boolean('Sync', default=False, help="Check to include this folder in sync")
    last_sync = fields.Datetime('Last Synced', readonly=True)
    
    # Use case filters
    download_product_content = fields.Boolean('Product Images & Descriptions', default=False, 
        help="Auto-download JPG images and TXT descriptions for products")
    download_import_data = fields.Boolean('Import Data', default=False, 
        help="Auto-download CSV/XLS/XLSX/TXT files for data imports")
    
    _sql_constraints = [
        ('folder_id_unique', 'UNIQUE(folder_id)', 'Folder ID must be unique!')
    ]


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    # Google Drive Settings
    gdrive_service_account_json = fields.Text(
        string='Service Account JSON',
        help='JSON content of your Google Service Account credentials'
    )
    
    # Time period selection
    gdrive_sync_time_period = fields.Selection([
        ('1', 'Last Day'),
        ('2', 'Last 2 Days'),
        ('7', 'Last Week'),
        ('14', 'Last 2 Weeks'),
        ('30', 'Last Month'),
        ('90', 'Last 3 Months'),
        ('180', 'Last 6 Months'),
        ('365', 'Last Year'),
        ('all', 'All Time'),
    ], string='Sync Time Period', default='7', required=True)
    
    
    # Auto-download batch size
    gdrive_auto_download_batch_size = fields.Integer(
        string='Auto-Download Batch Size',
        default=10,
        help='Number of files to download automatically per cron run'
    )
    # Computed field to show existing folders
    folder_count = fields.Integer(
        string='Folders Discovered',
        compute='_compute_folder_count',
        store=False
    )
    
    # JSON status field
    gdrive_json_status = fields.Char(
        string='JSON Status',
        compute='_compute_json_status',
        store=False
    )
    
    @api.depends('gdrive_service_account_json')
    def _compute_json_status(self):
        """Compute JSON configuration status"""
        for record in self:
            ICPSudo = record.env['ir.config_parameter'].sudo()
            existing_json = ICPSudo.get_param('gdrive.service_account_json', '')
            
            if record.gdrive_service_account_json:
                record.gdrive_json_status = "New JSON provided (will be saved)"
            elif existing_json:
                record.gdrive_json_status = "JSON configured"
            else:
                record.gdrive_json_status = "No JSON configured"
    
    @api.depends('gdrive_service_account_json')  # Add a dependency to trigger recompute
    def _compute_folder_count(self):
        """Count discovered folders"""
        for record in self:
            record.folder_count = self.env['gdrive.folder.selection'].search_count([])
    
    @api.model
    def default_get(self, fields_list):
        """Load values from system parameters"""
        res = super().default_get(fields_list)
        ICPSudo = self.env['ir.config_parameter'].sudo()
        
        res.update({
            'gdrive_sync_time_period': ICPSudo.get_param('gdrive.sync_time_period', '7'),
            'gdrive_auto_download_batch_size': int(ICPSudo.get_param('gdrive.auto_download_batch_size', '10')),
        })
        
        return res
    
    def set_values(self):
        """Save settings to system parameters"""
        super().set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        
        # Save JSON if provided
        if self.gdrive_service_account_json:
            ICPSudo.set_param('gdrive.service_account_json', self.gdrive_service_account_json)
        
        # Save time period
        ICPSudo.set_param('gdrive.sync_time_period', self.gdrive_sync_time_period)
        
        # Save auto-download batch size
        ICPSudo.set_param('gdrive.auto_download_batch_size', str(self.gdrive_auto_download_batch_size))
        
        _logger.info(f"Settings saved")
    
    def action_discover_folders(self):
        """Discover all folders from Google Drive"""
        json_content = self.gdrive_service_account_json
        if not json_content:
            json_content = self.env['ir.config_parameter'].sudo().get_param('gdrive.service_account_json', '')
        
        if not json_content:
            raise UserError(_('Please enter the Service Account JSON first.'))
        
        try:
            gdrive_model = self.env['gdrive.file']
            service = gdrive_model._get_drive_service(json_content)
            
            # Get all folders from Google Drive
            folders = self._get_all_folders(service)
            _logger.info(f"Found {len(folders)} folders from Google Drive")
            
            # Get existing folder records
            FolderSelection = self.env['gdrive.folder.selection']
            existing_folders = FolderSelection.search([])
            existing_folder_ids = {f.folder_id: f for f in existing_folders}
            
            folders_created = 0
            folders_updated = 0
            
            for folder in folders:
                folder_id = folder['id']
                
                if folder_id in existing_folder_ids:
                    # Update existing folder (in case name or path changed)
                    existing_folder = existing_folder_ids[folder_id]
                    if existing_folder.folder_name != folder['name'] or existing_folder.folder_path != folder['path']:
                        existing_folder.write({
                            'folder_name': folder['name'],
                            'folder_path': folder['path'],
                        })
                        folders_updated += 1
                else:
                    # Create new folder record
                    # Default: select top-level folders only
                    is_selected = '/' not in folder.get('path', '')
                    FolderSelection.create({
                        'folder_id': folder_id,
                        'folder_name': folder['name'],
                        'folder_path': folder['path'],
                        'selected': is_selected,
                    })
                    folders_created += 1
            
            # Remove folders that no longer exist in Google Drive
            current_folder_ids = {f['id'] for f in folders}
            folders_to_remove = existing_folders.filtered(lambda f: f.folder_id not in current_folder_ids)
            if folders_to_remove:
                folders_to_remove.unlink()
                _logger.info(f"Removed {len(folders_to_remove)} folders that no longer exist")
            
            message = _('Discovery complete!\n')
            if folders_created:
                message += _('• Created %d new folders\n') % folders_created
            if folders_updated:
                message += _('• Updated %d existing folders\n') % folders_updated
            if folders_to_remove:
                message += _('• Removed %d deleted folders\n') % len(folders_to_remove)
            message += _('\nTotal folders: %d') % len(folders)
            
            # Show notification and refresh the form
            self._compute_folder_count()  # Force recompute
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Folders Discovered'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f"Error discovering folders: {e}")
            raise UserError(_('Failed to discover folders: %s') % str(e))
    
    def action_view_folders(self):
        """Open the folder selection view"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Google Drive Folders',
            'res_model': 'gdrive.folder.selection',
            'view_mode': 'tree',
            'target': 'current'
        }
    
    def _get_all_folders(self, service):
        """Get all folders from Google Drive"""
        try:
            query = "mimeType='application/vnd.google-apps.folder'"
            
            all_folders = []
            page_token = None
            
            while True:
                results = service.files().list(
                    q=query,
                    fields="nextPageToken, files(id, name, parents)",
                    pageSize=100,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    corpora='allDrives',
                    pageToken=page_token
                ).execute()
                
                folders = results.get('files', [])
                all_folders.extend(folders)
                
                page_token = results.get('nextPageToken')
                if not page_token:
                    break
            
            # Build folder paths
            result_folders = []
            for folder in all_folders:
                folder_path = self._get_folder_path(service, folder['id'], folder['name'])
                result_folders.append({
                    'id': folder['id'],
                    'name': folder['name'],
                    'path': folder_path,
                })
            
            return sorted(result_folders, key=lambda x: x['path'])
            
        except Exception as e:
            _logger.error(f"Error getting folders: {str(e)}")
            raise
    
    def _get_folder_path(self, service, folder_id, folder_name):
        """Get full folder path"""
        try:
            folder_info = service.files().get(
                fileId=folder_id,
                fields="parents",
                supportsAllDrives=True
            ).execute()
            
            parents = folder_info.get('parents', [])
            if not parents or parents[0] == 'root':
                return folder_name
            
            try:
                parent_info = service.files().get(
                    fileId=parents[0],
                    fields="name,parents",
                    supportsAllDrives=True
                ).execute()
                parent_path = self._get_folder_path(service, parents[0], parent_info['name'])
                return f"{parent_path}/{folder_name}"
            except:
                return folder_name
                
        except:
            return folder_name
    
    def action_sync_now(self):
        """Trigger sync immediately"""
        # First save current settings
        self.set_values()
        
        # Then run sync
        return self.env['gdrive.file'].sync_google_drive_files()