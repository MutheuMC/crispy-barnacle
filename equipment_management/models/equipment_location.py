# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class EquipmentLocation(models.Model):
    _name = 'equipment.location'
    _description = 'Equipment Location'
    _order = 'complete_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'complete_name'

    name = fields.Char(
        string='Location Name',
        required=True,
        tracking=True,
        help='e.g., Main Store, Lab A, Lab B, Workshop'
    )
    code = fields.Char(
        string='Location Code',
        tracking=True,
        help='Short code for quick identification'
    )
    parent_id = fields.Many2one(
        'equipment.location',
        string='Parent Location',
        ondelete='cascade',
        tracking=True,
        help='Hierarchical location structure'
    )
    child_ids = fields.One2many(
        'equipment.location',
        'parent_id',
        string='Sub-locations'
    )
    complete_name = fields.Char(
        string='Full Location Path',
        compute='_compute_complete_name',
        store=True,
        recursive=True
    )
    
    # Address Details
    building = fields.Char(
        string='Building',
        tracking=True
    )
    floor = fields.Char(
        string='Floor',
        tracking=True
    )
    room = fields.Char(
        string='Room Number',
        tracking=True
    )
    address = fields.Text(
        string='Full Address'
    )
    
    # Responsible Person
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible Person',
        tracking=True,
        help='Person responsible for this location'
    )
    
    # Location Type
    location_type = fields.Selection([
        ('warehouse', 'Warehouse/Store'),
        ('lab', 'Laboratory'),
        ('office', 'Office'),
        ('workshop', 'Workshop'),
        ('field', 'Field/External'),
        ('maintenance', 'Maintenance Area'),
        ('retired', 'Retired/Disposal Area'),
    ], string='Location Type', default='lab', tracking=True)
    
    # Statistics
    equipment_count = fields.Integer(
        string='Equipment Count',
        compute='_compute_equipment_count',
        recursive = True

    )
    borrowed_count = fields.Integer(
        string='Currently Borrowed',
        compute='_compute_borrowed_count'
    )
    
    # Additional Fields
    active = fields.Boolean(
        default=True,
        help='If unchecked, it will allow you to hide the location without removing it.'
    )
    notes = fields.Text(
        string='Notes'
    )
    
    # GPS Coordinates (optional)
    latitude = fields.Float(
        string='Latitude',
        digits=(10, 7)
    )
    longitude = fields.Float(
        string='Longitude',
        digits=(10, 7)
    )

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Location code must be unique!'),
    ]

    @api.depends('name', 'parent_id.complete_name')
    def _compute_complete_name(self):
        """Build complete location path"""
        for location in self:
            if location.parent_id:
                location.complete_name = f"{location.parent_id.complete_name} / {location.name}"
            else:
                location.complete_name = location.name

    @api.depends('parent_id.equipment_count')
    def _compute_equipment_count(self):
        """Count equipment in this location"""
        for location in self:
            location.equipment_count = self.env['equipment.item'].search_count([
                ('location_id', '=', location.id)
            ])

    def _compute_borrowed_count(self):
        """Count currently borrowed equipment from this location"""
        for location in self:
            location.borrowed_count = self.env['equipment.loan'].search_count([
                ('from_location_id', '=', location.id),
                ('state', 'in', ['approved', 'issued'])
            ])

    def name_get(self):
        """Display location with code if available"""
        result = []
        for location in self:
            name = location.complete_name
            if location.code:
                name = f"[{location.code}] {name}"
            result.append((location.id, name))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        """Search by name or code"""
        args = args or []
        domain = []
        if name:
            domain = ['|', ('complete_name', operator, name), ('code', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

    def action_view_equipment(self):
        """View all equipment in this location"""
        self.ensure_one()
        return {
            'name': _('Equipment in %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.item',
            'view_mode': 'kanban,tree,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id},
        }