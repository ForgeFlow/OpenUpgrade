# Copyright 2020 ForgeFlow <https://www.forgeflow.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade


def create_pos_payment_methods(env):
    env.cr.execute("""
        SELECT DISTINCT journal_id
        FROM pos_config_journal_rel
    """)
    journal_ids = [aj[0] for aj in env.cr.fetchall()]
    if journal_ids:
        vals_list = []
        for journal in env['account.journal'].browse(journal_ids):
            vals = {
                'name': 'Cash',
                'cash_journal_id': journal.id,
                'is_cash_count': True,
                'company_id': journal.company_id.id,
                'receivable_account_id': journal.company_id.account_default_pos_receivable_account_id.id,
            }
            vals_list += [vals]
        env['pos.payment.method'].create(vals_list)
    openupgrade.logged_query(
        env.cr, """
        INSERT INTO pos_config_pos_payment_method_rel
            (pos_config_id, pos_payment_method_id)
        SELECT pos_config_id, ppm.id
        FROM pos_config_journal_rel pcjr
        JOIN account_journal aj ON pcjr.journal_id = aj.id
        JOIN pos_payment_method ppm ON ppm.cash_journal_id = aj.id""")


def create_pos_payments(env):
    env.cr.execute("""
        SELECT DISTINCT absl.id, ppm.id
        FROM account_bank_statement abs
        JOIN pos_session ps ON abs.pos_session_id = ps.id
        JOIN account_bank_statement_line absl ON absl.statement_id = abs.id
        LEFT JOIN account_journal aj ON abs.journal_id = aj.id
        JOIN pos_payment_method ppm ON ppm.cash_journal_id = aj.id
    """)
    st_lines_ids_dict = {stl[0]: stl[1] for stl in env.cr.fetchall()}
    if st_lines_ids_dict:
        vals_list = []
        for st_line in env['account.bank.statement.line'].browse(
                list(st_lines_ids_dict)):
            vals = {
                'name': st_line.name,
                'pos_order_id': st_line.pos_statement_id.id,
                'amount': st_line.amount,
                'payment_method_id': st_lines_ids_dict[st_line.id],
                'payment_date': st_line.create_date,
            }
            vals_list += [vals]
        env['pos.payment'].create(vals_list)


@openupgrade.migrate()
def migrate(env, version):
    create_pos_payment_methods(env)
    create_pos_payments(env)
