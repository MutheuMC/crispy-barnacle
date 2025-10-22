# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


# -------------------------------------------------------------------
# RETURN WIZARD  (updated per checklist)
# -------------------------------------------------------------------
class EquipmentLoanReturnWizard(models.TransientModel):
    _name = 'equipment.loan.return.wizard'
    _description = 'Equipment Loan Return Wizard'

    loan_id = fields.Many2one(
        'equipment.loan', string='Loan', required=True, readonly=True
    )
    equipment_id = fields.Many2one(
        'equipment.item', string='Equipment', related='loan_id.equipment_id', readonly=True
    )
    return_date = fields.Datetime(
        string='Return Date', required=True, default=fields.Datetime.now
    )
    return_location_id = fields.Many2one(
        'equipment.location', string='Return Location', required=True,
        help='Location where the equipment is returned'
    )
    condition_return = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ], string='Condition at Return', required=True, default='good')

    has_damage = fields.Boolean(string='Equipment Damaged')
    damage_notes = fields.Text(string='Damage Description')
    damage_cost = fields.Monetary(string='Estimated Repair Cost', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    returned_to_id = fields.Many2one(
        'res.users', string='Returned To', default=lambda self: self.env.user, required=True
    )

    notes = fields.Text(string='Return Notes')
    create_maintenance = fields.Boolean(string='Schedule Maintenance',
                                        help='Create a maintenance record after return')

    @api.onchange('has_damage')
    def _onchange_has_damage(self):
        if self.has_damage:
            self.condition_return = 'damaged'

    def action_confirm_return(self):
        """Process the return and transition equipment state:
           - maintenance -> state=maintenance, location=return_location
           - assigned holder exists -> state=assigned, keep location (do NOT force Main Store)
           - no holder -> state=available, location=return_location
        """
        self.ensure_one()

        if not self.loan_id or self.loan_id.state not in ['issued', 'overdue']:
            raise UserError(_('Only issued or overdue loans can be returned.'))

        # Prepare loan update with guards for optional fields
        loan_updates = {
            'state': 'returned',
            'return_date': self.return_date,
            'condition_return': self.condition_return,
            'damage_notes': self.damage_notes if self.has_damage else False,
            'damage_cost': self.damage_cost if self.has_damage else 0,
            'returned_to_id': self.returned_to_id.id,
        }
        if 'actual_return_location_id' in self.loan_id._fields:
            loan_updates['actual_return_location_id'] = self.return_location_id.id
        self.loan_id.write(loan_updates)

        eq = self.equipment_id.sudo()

        # Decide equipment state after return
        if self.create_maintenance:
            new_state = 'maintenance'
        elif eq.holder_type != 'none':
            new_state = 'assigned'
        else:
            new_state = 'available'

        # Build values; if assigned, keep current non-store location
        values = {
            'state': new_state,
            'condition': self.condition_return,
            'condition_notes': self.damage_notes if self.has_damage else eq.condition_notes,
        }
        if new_state in ('available', 'maintenance'):
            values['location_id'] = self.return_location_id.id

        # Do not write unknown fields (e.g., custodian_id) unless they exist
        if 'custodian_id' in eq._fields:
            values['custodian_id'] = False

        eq.write(values)

        # Auto-create maintenance if requested (compatible with equipment_id or equipment_ids)
        if self.create_maintenance:
            Maint = self.env['equipment.maintenance']
            vals = {
                'maintenance_type': 'corrective',
                'description': self.damage_notes or _('Maintenance required after return'),
                'scheduled_date': fields.Date.today(),
            }
            if 'equipment_id' in Maint._fields:
                vals['equipment_id'] = eq.id
            elif 'equipment_ids' in Maint._fields:
                vals['equipment_ids'] = [(4, eq.id)]
            if 'state' in Maint._fields and 'scheduled' in dict(Maint._fields['state'].selection):
                vals['state'] = 'scheduled'
            Maint.create(vals)

        # Notify + chatter
        self.loan_id._send_return_notification()
        message = _('Equipment returned successfully.')
        if self.has_damage:
            message += _('\n⚠️ Equipment has damage: %s') % self.damage_notes
        self.loan_id.message_post(body=message, subject=_('Equipment Returned'))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.loan',
            'res_id': self.loan_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


# -------------------------------------------------------------------
# REJECT WIZARD (logic kept)
# -------------------------------------------------------------------
class EquipmentLoanRejectWizard(models.TransientModel):
    _name = 'equipment.loan.reject.wizard'
    _description = 'Equipment Loan Rejection Wizard'

    loan_id = fields.Many2one('equipment.loan', string='Loan', required=True, readonly=True)
    rejection_reason = fields.Text(string='Reason for Rejection', required=True)
    notify_borrower = fields.Boolean(string='Notify Borrower', default=True)

    def action_confirm_reject(self):
        self.ensure_one()

        if self.loan_id.state not in ['draft', 'pending']:
            raise UserError(_('Only draft or pending loans can be rejected.'))

        self.loan_id.write({
            'state': 'cancelled',
            'rejection_reason': self.rejection_reason,
        })

        self.loan_id.message_post(
            body=_('Loan request rejected.\nReason: %s') % self.rejection_reason,
            subject=_('Loan Request Rejected')
        )

        if self.notify_borrower:
            self.loan_id.message_notify(
                partner_ids=self.loan_id.borrower_id.partner_id.ids,
                subject=_('Loan Request Rejected'),
                body=_('Your loan request %s has been rejected.\nReason: %s') % (
                    self.loan_id.name, self.rejection_reason
                )
            )

        return {'type': 'ir.actions.act_window_close'}


# -------------------------------------------------------------------
# QUICK BORROW WIZARD (blocks when assigned)
# -------------------------------------------------------------------

class EquipmentBorrowWizard(models.TransientModel):
    _name = 'equipment.borrow.wizard'
    _description = 'Quick Equipment Borrow Wizard'

    equipment_id = fields.Many2one('equipment.item', string='Equipment', required=True, readonly=True)

    borrower_type = fields.Selection([
        ('user', 'Internal User'),
        ('employee', 'Employee'),
        ('department', 'Department/Unit'),
        ('external', 'External Borrower'),
    ], string='Borrower Type', default='user', required=True)

    borrower_id = fields.Many2one('res.users', string='User',
                                  default=lambda self: self.env.user)
    borrower_employee_id = fields.Many2one('res.partner', string='Employee',
                                           domain="[('is_company','=',False)]")
    borrower_department_id = fields.Many2one('res.partner', string='Department/Unit',
                                             domain="[('is_company','=',True)]")
    borrower_partner_id = fields.Many2one('res.partner', string='External Borrower')

    borrow_date = fields.Datetime(string='Borrow Date', required=True, default=fields.Datetime.now)
    due_date = fields.Datetime(string='Due Date', required=True)
    purpose = fields.Text(string='Purpose', required=True)

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        if self.equipment_id and self.equipment_id.category_id.max_borrow_days:
            from datetime import timedelta
            days = self.equipment_id.category_id.max_borrow_days
            self.due_date = fields.Datetime.now() + timedelta(days=days)

    @api.onchange('borrower_type')
    def _onchange_borrower_type(self):
        if self.borrower_type == 'user':
            self.borrower_employee_id = False
            self.borrower_department_id = False
            self.borrower_partner_id = False
        elif self.borrower_type == 'employee':
            self.borrower_id = False
            self.borrower_department_id = False
            self.borrower_partner_id = False
        elif self.borrower_type == 'department':
            self.borrower_id = False
            self.borrower_employee_id = False
            self.borrower_partner_id = False
        else:
            self.borrower_id = False
            self.borrower_employee_id = False
            self.borrower_department_id = False

    def action_confirm_borrow(self):
        self.ensure_one()

        eq = self.equipment_id.sudo()
        if eq.holder_type != 'none':
            raise UserError(_('This item is assigned. Unassign it before borrowing.'))
        if eq.state not in ['available', 'reserved']:
            raise UserError(_('Equipment must be available or reserved to borrow.'))

        loan_vals = {
            'equipment_id': eq.id,
            'borrower_type': self.borrower_type,
            'borrow_date': self.borrow_date,
            'due_date': self.due_date,
            'purpose': self.purpose,
            'from_location_id': eq.location_id.id,
            'return_location_id': eq.location_id.id,
            'condition_out': eq.condition,
        }
        if self.borrower_type == 'user':
            loan_vals['borrower_id'] = (self.borrower_id or self.env.user).id
        elif self.borrower_type == 'employee':
            if not self.borrower_employee_id:
                raise ValidationError(_('Please select the Employee borrower.'))
            loan_vals['borrower_employee_id'] = self.borrower_employee_id.id
        elif self.borrower_type == 'department':
            if not self.borrower_department_id:
                raise ValidationError(_('Please select the Department borrower.'))
            loan_vals['borrower_department_id'] = self.borrower_department_id.id
        else:
            if not self.borrower_partner_id:
                raise ValidationError(_('Please select the External borrower.'))
            loan_vals['borrower_partner_id'] = self.borrower_partner_id.id

        loan = self.env['equipment.loan'].create(loan_vals)

        if not getattr(loan, 'requires_approval', False):
            loan.action_approve()
            loan.action_issue()
        else:
            loan.action_submit_for_approval()

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'equipment.loan',
            'res_id': loan.id,
            'view_mode': 'form',
            'target': 'current',
        }


# -------------------------------------------------------------------
# ASSIGN / UNASSIGN WIZARDS
# -------------------------------------------------------------------
class EquipmentAssignWizard(models.TransientModel):
    _name = 'equipment.assign.wizard'
    _description = 'Assign Equipment to Holder'

    equipment_id = fields.Many2one('equipment.item', string='Equipment', required=True, readonly=True)

    holder_type = fields.Selection([
        ('employee', 'Employee'),
        ('department', 'Department/Unit'),
        ('other', 'External Custodian'),
    ], required=True, default='employee')

    employee_id = fields.Many2one('res.partner', string='Employee', domain="[('is_company','=',False)]")
    department_id = fields.Many2one('res.partner', string='Department/Unit', domain="[('is_company','=',True)]")
    custodian_partner_id = fields.Many2one('res.partner', string='External Custodian')

    assigned_date = fields.Date(string='Assigned Date', required=True, default=fields.Date.today)
    notes = fields.Text(string='Notes')

    def _target_location_for_assignment(self):
        """If item is in Main Store, move it to a non-store location (prefer 'In Use')."""
        equipment = self.equipment_id
        ms = self.env.ref('equipment_management.location_main_store', raise_if_not_found=False)
        if not equipment.location_id or (ms and equipment.location_id.id == (ms.id if ms else 0)):
            in_use = self.env.ref('equipment_management.location_in_use', raise_if_not_found=False)
            if in_use:
                return in_use.id
            # fallback: any active non-store location
            any_loc = self.env['equipment.location'].search([
                ('id', '!=', ms.id if ms else 0), ('active', '=', True)
            ], limit=1)
            if not any_loc:
                raise UserError(_('Create at least one non-store location before assigning items.'))
            return any_loc.id
        return equipment.location_id.id

    def action_confirm_assign(self):
        self.ensure_one()
        eq = self.equipment_id.sudo()

        # Guard rails
        if eq.state == 'borrowed':
            raise UserError(_('Return this item before assigning it.'))
        if eq.state in ['maintenance', 'retired', 'lost']:
            raise UserError(_('Cannot assign items in maintenance/retired/lost state.'))

        # Validate holder & prepare values
        if self.holder_type == 'employee':
            if not self.employee_id:
                raise ValidationError(_('Please choose an Employee.'))
            holder_vals = {'employee_id': self.employee_id.id}
            holder_label = self.employee_id.display_name
        elif self.holder_type == 'department':
            if not self.department_id:
                raise ValidationError(_('Please choose a Department/Unit.'))
            holder_vals = {'department_id': self.department_id.id}
            holder_label = self.department_id.display_name
        else:  # 'other'
            if not self.custodian_partner_id:
                raise ValidationError(_('Please choose an External Custodian.'))
            holder_vals = {'custodian_partner_id': self.custodian_partner_id.id}
            holder_label = self.custodian_partner_id.display_name

        # Decide target location once; reuse for item + history (avoid race with eq.write)
        target_loc_id = self._target_location_for_assignment()

        # Close any existing open assignment (reassignment safety)
        open_asg = self.env['equipment.assignment'].search([
            ('equipment_id', '=', eq.id),
            ('unassigned_date', '=', False),
        ], limit=1)
        if open_asg:
            open_asg.write({
                'unassigned_date': self.assigned_date,
                'unassigned_by_id': self.env.user.id,
                'notes': (open_asg.notes or '') + '\n' + _('Auto-closed by reassignment.'),
            })

        # Write item (holder fields + date + move + state)
        vals = {
            'holder_type': self.holder_type,
            'employee_id': False,
            'department_id': False,
            'custodian_partner_id': False,
            'assigned_date': self.assigned_date,
            'location_id': target_loc_id,
            'state': 'assigned' if eq.state not in ['maintenance', 'retired', 'lost', 'reserved'] else eq.state,
        }
        vals.update(holder_vals)
        eq.write(vals)

        # Create assignment history (snapshot)
        self.env['equipment.assignment'].create({
            'equipment_id': eq.id,
            'holder_type': self.holder_type,
            'employee_id': holder_vals.get('employee_id'),
            'department_id': holder_vals.get('department_id'),
            'custodian_partner_id': holder_vals.get('custodian_partner_id'),
            'assigned_date': self.assigned_date,
            'assigned_by_id': self.env.user.id,
            'notes': self.notes or False,
            'location_id': target_loc_id,
        })

        # Chatter note
        msg = _('Assigned to %s on %s.') % (holder_label, self.assigned_date)
        if self.notes:
            msg += '\n' + self.notes
        eq.message_post(body=msg, subject=_('Equipment Assigned'))

        return {'type': 'ir.actions.act_window_close'}


class EquipmentUnassignWizard(models.TransientModel):
    _name = 'equipment.unassign.wizard'
    _description = 'Unassign Equipment from Holder'

    equipment_id = fields.Many2one('equipment.item', string='Equipment', required=True, readonly=True)
    unassigned_date = fields.Date(string='Unassigned Date', required=True, default=fields.Date.today)
    notes = fields.Text(string='Notes')

    def action_confirm_unassign(self):
        self.ensure_one()
        eq = self.equipment_id.sudo()

        if eq.state == 'borrowed':
            raise UserError(_('Return this item before unassigning it.'))

        ms = self.env.ref('equipment_management.location_main_store', raise_if_not_found=False)
        if not ms:
            raise UserError(_('Main Store location is missing. Please create it.'))

        # Close the open assignment record (guardrail: ensures no duplicate open assignments)
        open_asg = self.env['equipment.assignment'].search([
            ('equipment_id', '=', eq.id),
            ('unassigned_date', '=', False),
        ], limit=1)

        if not open_asg:
            raise UserError(_('No open assignment found for this equipment.'))

        # Update the assignment history with the unassignment details
        open_asg.write({
            'unassigned_date': self.unassigned_date,
            'unassigned_by_id': self.env.user.id,
            'notes': (open_asg.notes or '') + ('\n' + self.notes if self.notes else ''),
        })

        # Clear assignment fields on the equipment item
        vals = {
            'holder_type': 'none',
            'employee_id': False,
            'department_id': False,
            'custodian_partner_id': False,
            'assigned_date': False,
            'location_id': ms.id,
        }
        if eq.state not in ['maintenance', 'retired', 'lost', 'reserved']:
            vals['state'] = 'available'

        eq.write(vals)

        # Post message to chatter
        msg = _('Equipment unassigned on %s and moved to Main Store.') % self.unassigned_date
        if self.notes:
            msg += '\n' + _('Notes: %s') % self.notes
        eq.message_post(body=msg, subject=_('Equipment Unassigned'))

        return {'type': 'ir.actions.act_window_close'}
