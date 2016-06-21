# -*- coding: utf-8 -*-
# © 2016 Serpent Consulting Services Pvt. Ltd.
# © 2016 Eficent Business and IT Consulting Services S.L.
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).
from openerp import api, SUPERUSER_ID
from openupgradelib import openupgrade
from openerp.modules.registry import RegistryManager

def map_bank_state(cr):
    openupgrade.map_values(
        cr,
        openupgrade.get_legacy_name('state'), 'state',
        [('draft', 'open')],
        table='account_bank_statement', write='sql')

def map_type_tax_use(cr):
    openupgrade.map_values(
        cr,
        openupgrade.get_legacy_name('type_tax_use'), 'type_tax_use',
        [('all', 'none')],
        table='account_tax', write='sql')

def map_type_tax_use_template(cr):
    openupgrade.map_values(
        cr,
        openupgrade.get_legacy_name('type_tax_use'), 'type_tax_use',
        [('all', 'none')],
        table='account_tax_template', write='sql')

def map_journal_state(cr):
    openupgrade.map_values(
        cr,
        openupgrade.get_legacy_name('type'), 'type',
        [('purchase_refund', 'purchase'), ('sale_refund', 'sale'), ('situation', 'general')],
        table='account_journal', write='sql')

def account_templates(cr):
    # assign a chart template to configured companies in order not to
    # have the localization try to generate a new chart of accounts
    env = api.Environment(cr, SUPERUSER_ID, {})
    account_templates = env['account.chart.template'].search([])
    configurable_template = env.ref('account.configurable_chart_template')
    account_templates -= configurable_template
    cr.execute('select distinct company_id from account_account where active')
    for company in env['res.company'].browse([i for i, in cr.fetchall()]):
        if company.chart_template_id:
            # probably never happens, but we need to be sure not to overwrite
            # this anyways
            continue
        cr.execute(
            'select max(char_length(code)) from account_account '
            'where company_id=%s and parent_id is null', (company.id,))
        accounts_code_digits = cr.fetchall()[0][0]
        if len(account_templates) == 1:
            # if there's only one template, we can be quite sure that's the
            # right one
            company.write({
                'chart_template_id': account_templates.id,
                'accounts_code_digits': accounts_code_digits,
                'transfer_account_id': account_templates.transfer_account_id.id
            })
            continue
        # when there are multiple charts of accounts, things get messy.
        # we assign the chart of accounts with the most matches concerning
        # account codes (as names are more likely to change)
        best_template = configurable_template
        best_count = 0

        for template in account_templates:
            count = env['account.account'].search_count([
                ('code', 'in', template.account_ids.mapped('code')),
                ('company_id', '=', company.id),
            ])
            if count > best_count:
                best_count = count
                best_template = template
        openupgrade.message(
            cr, 'account', 'res_company', 'account_chart_template',
            'Fuzzily mapping company %d to chart template %d - this may be '
            'wrong', company, best_template)
        company.write({
            'chart_template_id': best_template.id,
            'accounts_code_digits': accounts_code_digits,
            'transfer_account_id': account_templates.transfer_account_id.id
        })

def parent_id_to_m2m(cr):
    cr.execute(
        'insert into account_tax_template_filiation_rel '
        '(parent_tax, child_tax) '
        'select id, parent_id from account_tax_template '
        'where parent_id is not null'
    )
    cr.execute(
        'insert into account_tax_filiation_rel '
        '(parent_tax, child_tax) '
        'select id, parent_id from account_tax where parent_id is not null'
    )

def cashbox(cr):

    cr.execute("""
    SELECT distinct bank_statement_id FROM account_cashbox_line
    """)

    bank_statement = cr.dictfetchall()

    for m in range(len(bank_statement)):

        bank_statement_id = bank_statement[m]['bank_statement_id']

        cr.execute("""
        SELECT pieces, number_opening FROM account_cashbox_line WHERE number_opening IS NOT NULL AND number_opening != 0 AND bank_statement_id  = %s
        """ %bank_statement_id)

        opening_cashbox = cr.dictfetchall()

        cr.execute("""
        INSERT INTO account_bank_statement_cashbox (create_date) VALUES (NULL) RETURNING id
        """)

        cashbox_id = cr.fetchone()[0]

        for x in opening_cashbox:
            opening_number = x['number_opening']
            pieces = x['pieces']
            cr.execute("""
            INSERT INTO account_cashbox_line (cashbox_id, number, coin_value) VALUES (%(cash_id)s, %(opening_number)s, %(pieces)s) 
            """ %{'opening_number' : opening_number, 'pieces' : pieces, 'cash_id' : cashbox_id})

        cr.execute("""
        UPDATE account_bank_statement SET cashbox_start_id = %s WHERE id = %s
        """ %(cashbox_id, bank_statement_id))

        cr.execute("""
        SELECT pieces, number_closing FROM account_cashbox_line WHERE number_closing IS NOT NULL AND bank_statement_id  = %s
        """ %bank_statement_id)

        closing_cashbox = cr.dictfetchall()

        cr.execute("""
        INSERT INTO account_bank_statement_cashbox (create_date) VALUES (NULL) RETURNING id
        """)

        cashbox_id = cr.fetchone()[0]

        for x in closing_cashbox:
            closing_number = x['number_closing']
            pieces = x['pieces']
            cr.execute("""
            INSERT INTO account_cashbox_line (cashbox_id, number, coin_value) VALUES (%(cash_id)s, %(closing_number)s, %(pieces)s) 
            """ %{'closing_number' : closing_number, 'pieces' : pieces, 'cash_id' : cashbox_id})

        cr.execute("""
        UPDATE account_bank_statement SET cashbox_end_id = %s WHERE id = %s
        """ %(cashbox_id, bank_statement_id))

def account_properties(cr):
    # Handle account properties as their names are changed.
    cr.execute("""
            update ir_property set name = 'property_account_payable_id', 
            fields_id = (select id from ir_model_fields where model 
            = 'res.partner' and name = 'property_account_payable_id') 
            where name = 'property_account_payable' and (res_id like 
            'res.partner%' or res_id is null)
            """)
    cr.execute("""
            update ir_property set fields_id = (select id from 
            ir_model_fields where model = 'res.partner' and 
            name = 'property_account_receivable_id'), name = 
            'property_account_receivable_id' where 
            name = 'property_account_receivable' and (res_id like 
            'res.partner%' or res_id is null)
            """)

@openupgrade.migrate()
def migrate(cr, version):
    map_bank_state(cr)
    map_type_tax_use(cr)
    map_type_tax_use_template(cr)
    map_journal_state(cr)
    account_templates(cr)
    parent_id_to_m2m(cr)
    cashbox(cr)
    account_properties(cr)

    # If the close_method is 'none', then set to 'False', otherwise set to 'True'
    cr.execute("""
    UPDATE account_account_type SET include_initial_balance =  CASE
    WHEN %(openupgrade)s = 'none' THEN False
    ELSE True
    END 
    """%{'openupgrade' : openupgrade.get_legacy_name('close_method')})

    # Set bank_statements_source to 'manual' 
    cr.execute("""
    UPDATE account_journal SET bank_statements_source = 'manual'
    """)

    # Value 'percentage_of_total' => 'percentage' 
    cr.execute("""
    UPDATE account_operation_template SET amount_type = 'percentage' WHERE amount_type = 'percentage_of_total' 
    """)

    anglo_saxon_installed = openupgrade.is_module_installed(cr, 'account_anglo_saxon')
    if anglo_saxon_installed:
        cr.execute("""
        UPDATE res_company SET anglo_saxon_accounting = True
        """)

    # deprecate accounts where active is False
    cr.execute("""
    UPDATE account_account SET deprecated = True WHERE active = False
    """)

    # Set display_on_footer to False
    cr.execute("""
    UPDATE account_journal SET display_on_footer = False
    """)

    # Logic to move from child_ids to children_tax_ids (o2m => m2m)
    cr.execute("""
    INSERT INTO account_tax_filiation_rel (parent_tax, child_tax) 
    SELECT parent_id, id from account_tax WHERE parent_id IS NOT NULL
    """)

    # Get parent_id and insert it into children_tax_ids (m2o => m2m)
    cr.execute("""
    INSERT INTO account_tax_template_filiation_rel (parent_tax, child_tax) 
    SELECT parent_id, id from account_tax_template WHERE parent_id IS NOT NULL
    """)

    # In v8, if child_depend == True, then in v9, set amount_type='group'
    cr.execute("""
    UPDATE account_tax SET amount_type = 'group'
    WHERE child_depend IS True
    """)
    cr.execute("""
    UPDATE account_tax_template SET amount_type = 'group'
    WHERE child_depend IS True
    """)

    registry = RegistryManager.get(cr.dbname)
    openupgrade.m2o_to_x2m(
    cr, registry['account.bank.statement.line'],
    'account_bank_statement_line',
    'journal_entry_ids',
    openupgrade.get_legacy_name('journal_entry_id'))
