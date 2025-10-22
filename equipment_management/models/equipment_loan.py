# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import timedelta


class EquipmentLoan(models.Model):
    _name = 'equipment.loan'
    _description = 'Equipment Loan'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'borrow_date desc, id desc'

    name = fields.Char(
        string='Loan Number',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help='Unique loan reference number'
    )
    
    # Equipment & Borrower
    equipment_id = fields.Many2one(
        'equipment.item',
        string='Equipment',
        required=True,
        ondelete='restrict',
        tracking=True
    )
    equipment_barcode = fields.Char(
        related='equipment_id.barcode',
        string='Equipment Barcode',
        readonly=True
    )
    borrower_id = fields.Many2one(
        'res.users',
        string='Borrower',
        required=True,
        default=lambda self: self.env.user,
        tracking=True
    )
    borrower_email = fields.Char(
        related='borrower_id.email',
        string='Email',
        readonly=True
    )
    borrower_phone = fields.Char(
        related='borrower_id.phone',
        string='Phone',
        readonly=True
    )
    
    # Dates
    borrow_date = fields.Datetime(
        string='Borrow Date',
        required=True,
        default=fields.Datetime.now,
        tracking=True,
        help='Date and time when equipment is borrowed'
    )
    due_date = fields.Datetime(
        string='Due Date',
        required=True,
        tracking=True,
        help='Expected return date'
    )
    return_date = fields.Datetime(
        string='Actual Return Date',
        readonly=True,
        tracking=True,
        help='Actual date when equipment was returned'
    )
    
    # Locations
    from_location_id = fields.Many2one(
        'equipment.location',
        string='From Location',
        required=True,
        tracking=True,
        help='Location where equipment is borrowed from'
    )
    return_location_id = fields.Many2one(
        'equipment.location',
        string='Return Location',
        tracking=True,
        help='Location where equipment should be returned'
    )
    actual_return_location_id = fields.Many2one(
        'equipment.location',
        string='Actual Return Location',
        readonly=True,
        help='Actual location where equipment was returned'
    )
    
    # Purpose & Notes
    purpose = fields.Text(
        string='Purpose of Borrowing',
        required=True,
        help='Reason for borrowing this equipment'
    )
    notes = fields.Text(
        string='Additional Notes'
    )
    
    # Condition Assessment
    condition_out = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ], string='Condition at Checkout', default='good', required=True, tracking=True)
    
    condition_return = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ], string='Condition at Return', tracking=True)
    
    damage_notes = fields.Text(
        string='Damage/Issue Notes',
        help='Details of any damage or issues found during return'
    )
    damage_cost = fields.Monetary(
        string='Estimated Damage Cost',
        currency_field='currency_id',
        help='Estimated cost of damage repair'
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: self.env.company.currency_id
    )
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
        ('overdue', 'Overdue'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    # Approval
    approver_id = fields.Many2one(
        'res.users',
        string='Approved By',
        readonly=True,
        tracking=True
    )
    approval_date = fields.Datetime(
        string='Approval Date',
        readonly=True
    )
    rejection_reason = fields.Text(
        string='Rejection Reason'
    )
    
    # Computed Fields
    is_overdue = fields.Boolean(
        string='Is Overdue',
        compute='_compute_is_overdue',
        store=True,
        help='True if return is past due date'
    )
    days_borrowed = fields.Integer(
        string='Days Borrowed',
        compute='_compute_days_borrowed',
        help='Number of days equipment has been borrowed'
    )
    days_overdue = fields.Integer(
        string='Days Overdue',
        compute='_compute_days_overdue',
        help='Number of days past due date'
    )
    requires_approval = fields.Boolean(
        string='Requires Approval',
        compute='_compute_requires_approval',
        help='Whether this loan requires manager approval'
    )
    
    # Issued/Returned By
    issued_by_id = fields.Many2one(
        'res.users',
        string='Issued By',
        readonly=True,
        help='User who issued the equipment'
    )
    returned_to_id = fields.Many2one(
        'res.users',
        string='Returned To',
        readonly=True,
        help='User who accepted the return'
    )
    
    # Additional Info
    company_id = fields.Many2one(
        'res.company',
        default=lambda self: self.env.company
    )
    
    _sql_constraints = [
        ('check_dates', 'CHECK(due_date >= borrow_date)',
         'Due date must be after borrow date!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('equipment.loan') or _('New')

        records = super(EquipmentLoan, self).create(vals_list)
        return records

    @api.depends('due_date', 'return_date', 'state')
    def _compute_is_overdue(self):
        """Check if loan is overdue"""
        now = fields.Datetime.now()
        for loan in self:
            if loan.state in ['issued', 'approved'] and not loan.return_date:
                loan.is_overdue = loan.due_date < now
            else:
                loan.is_overdue = False

    @api.depends('borrow_date', 'return_date')
    def _compute_days_borrowed(self):
        """Calculate days borrowed"""
        for loan in self:
            if loan.borrow_date:
                end_date = loan.return_date or fields.Datetime.now()
                delta = end_date - loan.borrow_date
                loan.days_borrowed = delta.days
            else:
                loan.days_borrowed = 0

    @api.depends('due_date', 'is_overdue')
    def _compute_days_overdue(self):
        """Calculate days overdue"""
        now = fields.Datetime.now()
        for loan in self:
            if loan.is_overdue and loan.due_date:
                delta = now - loan.due_date
                loan.days_overdue = delta.days
            else:
                loan.days_overdue = 0

    @api.depends('equipment_id.category_id.requires_approval')
    def _compute_requires_approval(self):
        """Check if approval is required"""
        for loan in self:
            loan.requires_approval = loan.equipment_id.category_id.requires_approval

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        """Set defaults based on equipment"""
        if self.equipment_id:
            self.from_location_id = self.equipment_id.location_id
            self.return_location_id = self.equipment_id.location_id
            self.condition_out = self.equipment_id.condition
            
            # Set default due date based on category
            if self.equipment_id.category_id.max_borrow_days:
                days = self.equipment_id.category_id.max_borrow_days
                self.due_date = fields.Datetime.now() + timedelta(days=days)

    @api.onchange('borrow_date')
    def _onchange_borrow_date(self):
        """Update due date when borrow date changes"""
        if self.borrow_date and self.equipment_id.category_id.max_borrow_days:
            days = self.equipment_id.category_id.max_borrow_days
            self.due_date = self.borrow_date + timedelta(days=days)

    @api.constrains('equipment_id', 'borrow_date', 'due_date', 'state')
    def _check_equipment_availability(self):
        """Check if equipment is available for the requested period"""
        for loan in self:
            if loan.state in ['draft', 'pending']:
                continue
                
            # Check for overlapping loans
            overlapping = self.search([
                ('equipment_id', '=', loan.equipment_id.id),
                ('id', '!=', loan.id),
                ('state', 'in', ['approved', 'issued']),
                '|',
                '&', ('borrow_date', '<=', loan.borrow_date), ('due_date', '>=', loan.borrow_date),
                '&', ('borrow_date', '<=', loan.due_date), ('due_date', '>=', loan.due_date),
            ])
            
            if overlapping:
                raise ValidationError(_(
                    'Equipment "%s" is already borrowed for the requested period.\n'
                    'Conflicting loan: %s'
                ) % (loan.equipment_id.name, overlapping[0].name))
            

    # Workflow Actions
    def action_submit_for_approval(self):
        """Submit loan for approval"""
        for loan in self:
            if loan.requires_approval:
                loan.write({'state': 'pending'})
                loan._send_approval_notification()
            else:
                loan.action_approve()

    def action_approve(self):
        for loan in self:
            if loan.equipment_id.holder_type != 'none':
                raise UserError(_('This item is assigned to someone. Unassign it before borrowing.'))
            if loan.equipment_id.state not in ['available', 'reserved']:
                raise UserError(_('Equipment is not available for borrowing.'))
            loan.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'approval_date': fields.Datetime.now(),
            })
            loan._send_approval_notification()

    def action_reject(self):
        """Reject loan request"""
        return {
            'name': _('Reject Loan'),
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.loan.reject.wizard',
            'view_mode': 'form',
            'context': {'default_loan_id': self.id},
            'target': 'new',
        }

    def action_issue(self):
        for loan in self:
            if loan.equipment_id.holder_type != 'none':
                raise UserError(_('This item is assigned to someone. Unassign it before borrowing.'))
            if loan.state not in ['approved', 'draft']:
                raise UserError(_('Only approved loans can be issued.'))
            loan.equipment_id.write({
                'state': 'borrowed',
                'custodian_id': loan.borrower_id.id,
                'location_id': loan.from_location_id.id,  # keep a valid location
            })
            loan.write({
                'state': 'issued',
                'issued_by_id': self.env.user.id,
                'borrow_date': fields.Datetime.now(),
            })
            loan._send_issue_notification()


    def action_return(self):
        """Return equipment"""
        self.ensure_one()
        return {
            'name': _('Return Equipment'),
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.loan.return.wizard',
            'view_mode': 'form',
            'context': {
                'default_loan_id': self.id,
                'default_return_location_id': self.return_location_id.id,
                'default_condition_return': self.equipment_id.condition,
            },
            'target': 'new',
        }

    def action_cancel(self):
        """Cancel loan"""
        for loan in self:
            if loan.state == 'issued':
                raise UserError(_('Cannot cancel an issued loan. Please return the equipment first.'))
            
            loan.write({'state': 'cancelled'})
            loan.message_post(body=_('Loan cancelled.'))


    # Notification Methods
    def _send_approval_notification(self):
        """Send notification when loan is submitted/approved"""
        for loan in self:
            if loan.state == 'pending':
                # Notify managers
                managers = self.env.ref('equipment_management.group_equipment_manager').users
                loan.message_notify(
                    partner_ids=managers.mapped('partner_id').ids,
                    subject=_('Equipment Loan Approval Required'),
                    body=_('Loan %s requires your approval.\nEquipment: %s\nBorrower: %s') % (
                        loan.name, loan.equipment_id.name, loan.borrower_id.name
                    )
                )
            elif loan.state == 'approved':
                # Notify borrower
                loan.message_notify(
                    partner_ids=loan.borrower_id.partner_id.ids,
                    subject=_('Equipment Loan Approved'),
                    body=_('Your loan request %s has been approved.\nPlease collect the equipment.') % loan.name
                )

    def _send_issue_notification(self):
        """Send notification when equipment is issued"""
        for loan in self:
            loan.message_notify(
                partner_ids=loan.borrower_id.partner_id.ids,
                subject=_('Equipment Issued'),
                body=_('Equipment %s has been issued to you.\nDue date: %s') % (
                    loan.equipment_id.name,
                    loan.due_date.strftime('%Y-%m-%d %H:%M')
                )
            )

    def _send_return_notification(self):
        """Send notification when equipment is returned"""
        for loan in self:
            loan.message_notify(
                partner_ids=loan.borrower_id.partner_id.ids,
                subject=_('Equipment Returned'),
                body=_('Equipment %s has been returned successfully.') % loan.equipment_id.name
            )

    # Scheduled Actions
    @api.model
    def _cron_check_overdue_loans(self):
        """Check for overdue loans and send notifications"""
        overdue_loans = self.search([
            ('state', '=', 'issued'),
            ('due_date', '<', fields.Datetime.now()),
        ])
        
        for loan in overdue_loans:
            loan.write({'state': 'overdue'})
            loan.message_post(
                body=_('This loan is now overdue. Please return the equipment immediately.'),
                subject=_('Overdue Equipment'),
                partner_ids=loan.borrower_id.partner_id.ids
            )

    @api.model
    def _cron_send_due_reminders(self):
        """Send reminders for loans due tomorrow"""
        tomorrow = fields.Datetime.now() + timedelta(days=1)
        due_soon_loans = self.search([
            ('state', '=', 'issued'),
            ('due_date', '>=', fields.Datetime.now()),
            ('due_date', '<=', tomorrow),
        ])
        
        for loan in due_soon_loans:
            loan.message_notify(
                partner_ids=loan.borrower_id.partner_id.ids,
                subject=_('Equipment Return Reminder'),
                body=_('Reminder: Equipment %s is due tomorrow (%s).') % (
                    loan.equipment_id.name,
                    loan.due_date.strftime('%Y-%m-%d %H:%M')
                )
            )