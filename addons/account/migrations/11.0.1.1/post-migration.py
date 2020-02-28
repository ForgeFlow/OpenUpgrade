# Copyright 2017 bloopark systems (<http://bloopark.de>)
# Copyright 2018 Opener B.V. <https://opener.amsterdam>
# Copyright 2018-2019 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from psycopg2.extensions import AsIs
from openupgradelib import openupgrade


def migrate_account_tax_cash_basis(env):
    # Migrate tax exigibility settings
    if not openupgrade.column_exists(
            env.cr, 'account_tax',
            openupgrade.get_legacy_name('use_cash_basis')):
        return  # pragma: no cover
    field = AsIs(openupgrade.get_legacy_name('use_cash_basis'))
    openupgrade.logged_query(
        env.cr,
        """UPDATE account_tax
        SET tax_exigibility = 'on_payment'
        WHERE %s IS TRUE;""", (field,))
    openupgrade.logged_query(
        env.cr,
        """UPDATE account_tax
        SET tax_exigibility = 'on_invoice'
        WHERE %s IS NOT TRUE;""", (field,))
    openupgrade.logged_query(
        env.cr,
        """UPDATE res_company rc
        SET tax_exigibility = TRUE WHERE EXISTS (
            SELECT id FROM account_tax
            WHERE company_id = rc.id AND tax_exigibility = 'on_payment')""")


@openupgrade.logging()
def fill_account_invoice_line_total(env):
    """Try to compute the field `price_total` in a more optimized way for
    speeding up the migration.
    """
    # We first set price_subtotal for lines without taxes
    line_obj = env['account.invoice.line']
    empty_lines = line_obj.search([('invoice_line_tax_ids', '=', 'False')])
    if empty_lines:
        openupgrade.logged_query(
            env.cr, """
            UPDATE account_invoice_line
            SET price_total = price_subtotal
            WHERE id IN %s""", (tuple(empty_lines.ids), )
        )
    # Now we compute easily the lines with only 1 tax, no included in price,
    # and that tax is simply a percentage (which are most of the cases)
    env.cr.execute(
        """SELECT id FROM (
            SELECT ail.id,
                COUNT(at.id) AS rnum,
                MIN(CASE WHEN at.amount_type = 'percent' THEN 0 ELSE 1 END)
                    AS amount_type,
                MIN(CASE WHEN at.price_include THEN 0 ELSE 1 END)
                    AS price_include
            FROM account_invoice_line ail,
                account_invoice_line_tax rel,
                account_tax at
            WHERE
                ail.id = rel.invoice_line_id
                AND at.id = rel.tax_id
            GROUP BY ail.id
        ) sub
        WHERE sub.rnum = 1
            AND sub.amount_type = 0
            AND sub.price_include = 1"""
    )
    simple_lines = line_obj.browse([x[0] for x in env.cr.fetchall()])
    if simple_lines:
        openupgrade.logged_query(
            env.cr, """
            UPDATE account_invoice_line ail
            SET price_total = ail.price_subtotal + round(
                ail.price_unit * ail.quantity *
                (1 - COALESCE(ail.discount, 0.0) / 100.0) *
                at.amount / 100.0, CEIL(LOG(1.0 / cur.rounding))::INTEGER)
            FROM account_tax at,
                account_invoice_line_tax rel,
                account_invoice ai,
                res_currency cur
            WHERE ail.id = rel.invoice_line_id
                AND at.id = rel.tax_id
                AND ai.id = ail.invoice_id
                AND cur.id = ai.currency_id
                AND ail.id IN %s""", (tuple(simple_lines.ids), ),
        )
    # Compute the rest (which should be minority) with regular method
    rest_lines = line_obj.search([]) - empty_lines - simple_lines
    openupgrade.logger.debug("Compute the rest of the account.invoice.line"
                             "totals: %s" % len(rest_lines))
    for line in rest_lines:
        # avoid error on taxes with other type of computation ('code' for
        # example, provided by module `account_tax_python`). We will need to
        # add the computation on the corresponding module post-migration.
        types = ['percent', 'fixed', 'group', 'division']
        if any(x.amount_type not in types for x in line.invoice_line_tax_ids):
            continue
        # This has been extracted from `_compute_price` method
        currency = line.invoice_id and line.invoice_id.currency_id or None
        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
        taxes = line.invoice_line_tax_ids.compute_all(
            price, currency, line.quantity, product=line.product_id,
            partner=line.invoice_id.partner_id,
        )
        line.price_total = taxes['total_included']
    openupgrade.logger.debug("Compute finished")


@openupgrade.logging()
def fill_account_move_line_tax_base_amount(env):
    """Compute the field `tax_base_amount` in a more optimized way for speeding
    up the migration.
    """
    # First, put 0 on all of them without originator tax
    openupgrade.logged_query(
        env.cr, """
        UPDATE account_move_line
        SET tax_base_amount = 0
        WHERE tax_line_id IS NULL""",
    )
    # Then, get from SQL the sum of bases for the rest
    openupgrade.logged_query(
        env.cr, """
        UPDATE account_move_line aml
        SET tax_base_amount = sub.base
        FROM (
            SELECT aml.move_id, rel.account_tax_id, SUM(aml.balance) AS base
            FROM account_move_line aml,
                account_move_line_account_tax_rel rel
            WHERE aml.id = rel.account_move_line_id
            GROUP BY aml.move_id, rel.account_tax_id
        ) AS sub
        WHERE sub.move_id = aml.move_id
            AND sub.account_tax_id = aml.tax_line_id
        """,
    )


@openupgrade.logging()
def fill_account_invoice_tax_base_amount(env):
    AccountTax = env['account.tax']
    ResCurrency = env["res.currency"]
    ProductProduct = env["product.product"]
    AccountInvoiceTax = env["account.invoice.tax"]
    tax_grouped = {}
    # We group account invoice tax that have the same price_unit, discount,
    # currency_id, quantity, product_id and invoice_line_tax_ids, account_id
    # amd invoice_type since they will have the same base_amount value
    env.cr.execute("""
        SELECT STRING_AGG(invoice_id::CHARACTER varying, ',') invoice_id, 
                price_unit, discount, currency_id,
                quantity, product_id, tax_id, account_id, invoice_type
        FROM (
            SELECT aml.*, ailt.tax_id AS tax_id, ai.TYPE AS invoice_type
            FROM account_invoice_line AS aml
            LEFT JOIN (
                    SELECT invoice_line_id, 
                            STRING_AGG(tax_id::CHARACTER varying, ',') tax_id
                    FROM account_invoice_line_tax
                    GROUP BY invoice_line_id) AS ailt
                ON aml.id = ailt.invoice_line_id
            LEFT JOIN account_invoice AS ai
                ON ai.id = aml.invoice_id
            WHERE tax_id IS NOT NULL) AS sub
        GROUP BY price_unit, discount, currency_id, quantity, product_id, 
                tax_id, account_id, invoice_type;
    """)

    # We iterate over every group of account invoice tax where:
    # row[0] : (invoice_1, invoice_id_2, ...) invoice_ids
    # row[1] : price_unit
    # row[2] : discount
    # row[3] : currency_id
    # row[4] : quantity
    # row[5] : product_id
    # row[6] : (tax_id_1, tax_id_2, ...) invoice_line_tax_ids
    # row[7] : account_id
    # row[8] : invoice_type
    for row in env.cr.fetchall():
        # We compute the taxes for the group
        price = row[1] * (1 - (row[2] or 0.0) / 100.0)
        invoice_line_tax_ids = AccountTax.browse(
            [int(line_id) for line_id in row[6].split(",")])
        currency_id = ResCurrency.browse(
            int(row[3])) if row[3] else None
        round_curr = currency_id.round
        product_id = ProductProduct.browse(
            int(row[5])) if row[5] else None
        taxes = invoice_line_tax_ids.compute_all(
            price, currency_id, row[4], product=product_id,
            partner=False)['taxes']

        # For every invoice in this group we compute the tax_grouped dict
        # Code from Odoo adapted
        for invoice_id in [int(invoice_id) for invoice_id in
                           row[0].split(",")]:
            if invoice_id not in tax_grouped:
                tax_grouped[invoice_id] = {}
            for tax in taxes:
                val = {
                    'tax_id': tax['id'],
                    'amount': tax['amount'],
                    'base': tax['base'],
                    'account_id': (
                            row[8] in ('out_invoice', 'in_invoice') and (
                            tax['account_id'] or row[7]) or (
                            tax['refund_account_id'] or row[7])
                    ),
                }
                key = env['account.tax'].browse(tax['id']).get_grouping_key({
                    'tax_id': val["tax_id"],
                    'account_id': val["account_id"],
                    'account_analytic_id': False,
                })
                if key not in tax_grouped[invoice_id]:
                    tax_grouped[invoice_id][key] = val
                    tax_grouped[invoice_id][key]['base'] = round_curr(
                        val['base'])
                else:
                    tax_grouped[invoice_id][key]['amount'] += val['amount']
                    tax_grouped[invoice_id][key]['base'] += round_curr(
                        val['base'])

    # Compute base_amount for every account_invoice_tax. Code taken from Odoo
    for tax in AccountInvoiceTax.search([]):
        tax.base = 0.0
        if tax.tax_id:
            key = tax.tax_id.get_grouping_key({
                'tax_id': tax.tax_id.id,
                'account_id': tax.account_id.id,
                'account_analytic_id': tax.account_analytic_id.id,
            })
            if tax.invoice_id and key in tax_grouped[tax.invoice_id.id]:
                tax.base = tax_grouped[tax.invoice_id.id][key]['base']
            else:
                openupgrade.logger.debug(
                    'Tax Base Amount not computable probably due to a change '
                    'in an underlying tax (%s).',
                    tax.tax_id.name)


@openupgrade.migrate()
def migrate(env, version):
    # map old / non existing value 'proforma' and 'proforma2' to value 'draft'
    openupgrade.map_values(
        env.cr,
        openupgrade.get_legacy_name('state'), 'state',
        [('proforma', 'draft'), ('proforma2', 'draft')],
        table='account_invoice', write='sql')
    # copy statement_line_id values from account.move to account.move.line
    env.cr.execute("""
        UPDATE account_move_line aml
        SET statement_line_id = am.statement_line_id
        FROM account_move am
        WHERE aml.move_id = am.id AND am.statement_line_id IS NOT NULL;
    """)
    # Migrate draft payments to cancelled if they don't have any move lines
    # but they have been posted before (i.e. when move_name is set)
    openupgrade.logged_query(
        env.cr,
        """UPDATE account_payment
        SET state = 'cancelled'
        WHERE state = 'draft' AND move_name IS NOT NULL
        AND id NOT IN (
            SELECT payment_id FROM account_move_line
            WHERE payment_id IS NOT NULL)""")
    # Populate new 'sequence' field according to previous order field 'name'
    openupgrade.logged_query(
        env.cr,
        """UPDATE account_payment_term apt
        SET sequence = sub.sequence
        FROM (SELECT id, row_number() over (ORDER BY name asc) AS sequence
              FROM account_payment_term) sub
        WHERE sub.id = apt.id """)
    # Set accounting configuration steps to done if there are moves
    openupgrade.logged_query(
        env.cr,
        """UPDATE res_company rc
        SET account_setup_bank_data_done = TRUE,
            account_setup_bar_closed = TRUE,
            account_setup_coa_done = TRUE,
            account_setup_company_data_done = TRUE,
            account_setup_fy_data_done = TRUE
        WHERE EXISTS (
            SELECT id FROM account_move
            WHERE company_id = rc.id)""")

    migrate_account_tax_cash_basis(env)
    fill_account_invoice_tax_base_amount(env)
    fill_account_invoice_line_total(env)
    fill_account_move_line_tax_base_amount(env)

    openupgrade.load_data(
        env.cr, 'account', 'migrations/11.0.1.1/noupdate_changes.xml',
    )
