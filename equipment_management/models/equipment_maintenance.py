# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class EquipmentMaintenance(models.Model):
    _name = 'equipment.maintenance'
    _description = 'Equipment Maintenance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'scheduled_date desc'

    name = fields.Char(
        string='Maintenance Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    equipment_id = fields.Many2one(
        'equipment.item',
        string='Equipment',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    
 
    maintenance_type = fields.Selection([
        ('preventive', 'Preventive'),
        ('corrective', 'Corrective'),
        ('inspection', 'Inspection'),
        ('calibration', 'Calibration'),
    ], string='Type', required=True, default='preventive', tracking=True)
    
    description = fields.Text(
        string='Description',
        required=True,
        help='Details of maintenance work required'
    )
    scheduled_date = fields.Date(
        string='Scheduled Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    completed_date = fields.Date(
        string='Completed Date',
        readonly=True,
        tracking=True
    )
    technician_id = fields.Many2one(
        'res.users',
        string='Technician',
        tracking=True,
        help='Person responsible for maintenance'
    )
    state = fields.Selection([
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='scheduled', required=True, tracking=True)
    
    # Maintenance Details
    work_done = fields.Text(
        string='Work Done',
        help='Details of completed maintenance'
    )
    parts_used = fields.Text(
        string='Parts Used',
        help='List of parts/consumables used'
    )
    cost = fields.Monetary(
        string='Cost',
        currency_field='currency_id',
        help='Total cost of maintenance'
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    
    # Duration
    duration = fields.Float(
        string='Duration (hours)',
        help='Time spent on maintenance'
    )
    
    # Next Maintenance
    next_maintenance_date = fields.Date(
        string='Next Maintenance',
        help='When next maintenance is due'
    )
    
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('equipment.maintenance') or _('New')
        return super(EquipmentMaintenance, self).create(vals_list)

    def action_start(self):
        """Start maintenance work"""
        for maintenance in self:
            maintenance.write({
                'state': 'in_progress',
                'technician_id': self.env.user.id
            })
            # Update equipment status
            maintenance.equipment_id.write({'state': 'maintenance'})

    def action_complete(self):
        """Complete maintenance"""
        for maintenance in self:
            maintenance.write({
                'state': 'completed',
                'completed_date': fields.Date.today()
            })
            # Return equipment to available
            if maintenance.equipment_id.state == 'maintenance':
                maintenance.equipment_id.write({'state': 'available'})

    def action_cancel(self):
        """Cancel maintenance"""
        for maintenance in self:
            maintenance.write({'state': 'cancelled'})


class EquipmentReservation(models.Model):
    _name = 'equipment.reservation'
    _description = 'Equipment Reservation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'from_date desc'

    name = fields.Char(
        string='Reservation Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    equipment_ids = fields.Many2many(
        'equipment.item',
        'equipment_reservation_rel',   # <-- same table name
        'reservation_id',              # <-- this model’s FK column
        'equipment_id',                # <-- other model’s FK column
        string='Equipment',
        required=True,
    )
    from_date = fields.Datetime(
        string='From',
        required=True,
        tracking=True
    )
    to_date = fields.Datetime(
        string='To',
        required=True,
        tracking=True
    )
    purpose = fields.Text(
        string='Purpose',
        required=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True
    )
    notes = fields.Text(
        string='Notes'
    )
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                # Use a reservation sequence code you actually define; or keep 'New'
                vals['name'] = self.env['ir.sequence'].next_by_code('equipment.reservation') or _('New')

        # super() must target EquipmentReservation, not EquipmentMaintenance
        records = super(EquipmentReservation, self).create(vals_list)
        return records


    def action_submit(self):
        """Submit for approval"""
        for reservation in self:
            reservation.write({'state': 'pending'})

    def action_approve(self):
        """Approve reservation"""
        for reservation in self:
            reservation.write({
                'state': 'approved',
                'approver_id': self.env.user.id
            })
            # Mark equipment as reserved
            reservation.equipment_ids.write({'state': 'reserved'})

    def action_reject(self):
        """Reject reservation"""
        for reservation in self:
            reservation.write({'state': 'rejected'})

    def action_confirm(self):
        """Confirm pickup and create loans"""
        for reservation in self:
            # Create loan for each equipment
            for equipment in reservation.equipment_ids:
                self.env['equipment.loan'].create({
                    'equipment_id': equipment.id,
                    'borrower_id': reservation.requester_id.id,
                    'borrow_date': reservation.from_date,
                    'due_date': reservation.to_date,
                    'purpose': reservation.purpose,
                    'from_location_id': equipment.location_id.id,
                    'return_location_id': equipment.location_id.id,
                    'state': 'approved',
                })
            reservation.write({'state': 'confirmed'})