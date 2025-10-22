# -*- coding: utf-8 -*-
# equipment_management/models/equipment_assignment.py

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EquipmentAssignment(models.Model):
    _name = 'equipment.assignment'
    _description = 'Equipment Assignment History'
    _order = 'assigned_date desc, id desc'
    _rec_name = 'display_name'

    equipment_id = fields.Many2one('equipment.item', required=True, index=True, ondelete='cascade')
    holder_type = fields.Selection([
        ('employee', 'Employee'),
        ('department', 'Department/Unit'),
        ('other', 'External Custodian'),
    ], required=True, index=True)

    employee_id = fields.Many2one('res.partner', domain="[('is_company','=',False)]")
    department_id = fields.Many2one('res.partner', domain="[('is_company','=',True)]")
    custodian_partner_id = fields.Many2one('res.partner')

    assigned_date = fields.Date(required=True)
    unassigned_date = fields.Date()

    assigned_by_id = fields.Many2one('res.users', default=lambda s: s.env.user, required=True)
    unassigned_by_id = fields.Many2one('res.users')

    notes = fields.Text()
    # optional snapshot of location at assignment time
    location_id = fields.Many2one('equipment.location', string='Location at Assignment')

    display_name = fields.Char(compute='_compute_display_name', store=False)

    @api.depends('holder_type','employee_id','department_id','custodian_partner_id','assigned_date','unassigned_date')
    def _compute_display_name(self):
        for rec in self:
            who = (rec.employee_id or rec.department_id or rec.custodian_partner_id).name or _('Unknown')
            if rec.unassigned_date:
                rec.display_name = _('%(who)s (from %(a)s to %(b)s)') % {
                    'who': who, 'a': rec.assigned_date or '', 'b': rec.unassigned_date or ''
                }
            else:
                rec.display_name = _('%(who)s (since %(a)s)') % {'who': who, 'a': rec.assigned_date or ''}

    @api.constrains('equipment_id', 'unassigned_date')
    def _check_single_open_assignment(self):
        for rec in self:
            open_asg = self.search_count([
                ('equipment_id', '=', rec.equipment_id.id),
                ('id', '!=', rec.id),
                ('unassigned_date', '=', False),
            ])
            if open_asg:
                raise ValidationError(_('There can be only one active assignment per item.'))