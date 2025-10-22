# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EquipmentCategory(models.Model):
    _name = 'equipment.category'
    _description = 'Equipment Category'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Category Name',
        required=True,
        tracking=True,
        help='e.g., Monitors, PLCs, Instruments, Power Extensions'
    )
    code = fields.Char(
        string='Code',
        tracking=True,
        help='Short code for this category'
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Used to order categories'
    )
    parent_id = fields.Many2one(
        'equipment.category',
        string='Parent Category',
        ondelete='cascade',
        tracking=True
    )
    child_ids = fields.One2many(
        'equipment.category',
        'parent_id',
        string='Subcategories'
    )
    color = fields.Integer(
        string='Color',
        help='Color for kanban view'
    )
    
    # Borrowing Rules
    requires_approval = fields.Boolean(
        string='Requires Approval',
        default=False,
        tracking=True,
        help='Check if loans for this category need manager approval'
    )
    max_borrow_days = fields.Integer(
        string='Maximum Borrow Days',
        default=7,
        tracking=True,
        help='Default maximum number of days items can be borrowed'
    )
    allow_external_borrowing = fields.Boolean(
        string='Allow External Borrowing',
        default=False,
        tracking=True,
        help='Allow people outside the organization to borrow'
    )
    
    # Statistics
    equipment_count = fields.Integer(
        string='Equipment Count',
        compute='_compute_equipment_count',
        recursive=True,
        store=True
    )
    active = fields.Boolean(
        default=True,
        help='If unchecked, it will allow you to hide the category without removing it.'
    )
    
    # Additional Info
    description = fields.Text(
        string='Description'
    )
    image = fields.Binary(
        string='Image',
        help='Category image'
    )
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        tracking=True,
        help='Person responsible for this category'
    )
    
    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Category name must be unique!'),
    ]

    @api.depends('child_ids.equipment_count')
    def _compute_equipment_count(self):
        """Compute total equipment in this category and subcategories"""
        for category in self:
            equipment_count = self.env['equipment.item'].search_count([
                ('category_id', '=', category.id)
            ])
            # Add count from subcategories
            if category.child_ids:
                for child in category.child_ids:
                    equipment_count += child.equipment_count
            category.equipment_count = equipment_count

    @api.constrains('parent_id')
    def _check_category_recursion(self):
        """Prevent circular references in category hierarchy"""
        if not self._check_recursion():
            raise ValidationError(_('Error! You cannot create recursive categories.'))

    def name_get(self):
        """Display full path of category"""
        result = []
        for category in self:
            name = category.name
            if category.parent_id:
                name = f"{category.parent_id.name} / {name}"
            result.append((category.id, name))
        return result

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None):
        """Enhanced search including parent categories"""
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('code', operator, name)]
        return self._search(domain + args, limit=limit, access_rights_uid=name_get_uid)

    def action_view_equipment(self):
        """Open equipment items in this category"""
        self.ensure_one()
        return {
            'name': _('Equipment in %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.item',
            'view_mode': 'kanban,tree,form',
            'domain': [('category_id', '=', self.id)],
            'context': {'default_category_id': self.id},
        }