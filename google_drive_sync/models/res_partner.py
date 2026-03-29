# -*- coding: utf-8 -*-
from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    gds_last_import_date = fields.Date(
        string='Last Import Date',
        help='Date of last CSV import from Google Drive'
    )