# -*- coding: utf-8 -*-
{
    'name': 'Lab Equipment Management',
    'version': '18.0.1.0.1',
    'category': 'Inventory/Inventory',
    'summary': 'Manage lab equipment borrowing, tracking, and reservations',
    'description': """
        Lab Equipment Management System
        ================================
        * Equipment registry with QR/Barcode support
        * Camera-based scanning for quick check-in/out
        * Borrowing and reservation system
        * Location and custodian tracking
        * Maintenance scheduling
        * Mobile-friendly interface
    """,
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'depends': [
        'base',
        'mail',
        'web',
        'barcodes',
        'portal',
        'purchase',
    ],
    'data': [
        # Security
        'security/equipment_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/equipment_sequence.xml',
        'data/equipment_data.xml',
        
        # Views
        'views/equipment_category_views.xml',
        'views/equipment_location_views.xml',
        'views/equipment_item_views.xml',
        'views/equipment_loan_views.xml',
        'views/equipment_wizard_views.xml',
        'views/equipment_menus.xml',
        'views/equipment_item_server_actions.xml',
        'views/equipment_maintenance_views.xml',
        
        # Reports
        'reports/equipment_reports.xml',
        'reports/equipment_barcode_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'equipment_management/static/src/js/equipment_barcode_scanner.js',
            'equipment_management/static/src/xml/equipment_barcode_scanner.xml',
            'equipment_management/static/src/css/equipment_styles.css',
        ],
    },
    'demo': [
        'demo/equipment_demo.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}