# © 2018 Opener B.V. (stefan@opener.amsterdam)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade, openupgrade_merge_records


def generate_thumbnails(env):
    """ Let Odoo create a thumbnail for all attachments that consist of one of
    the supported image types and are not linked to a binary field. """
    for chunk in openupgrade.chunked(
            env['ir.attachment'].search([
                ('res_field', '=', False),
                ('mimetype', 'like', 'image.%'),
                '|', ('mimetype', 'like', '%gif'),
                '|', ('mimetype', 'like', '%jpeg'),
                '|', ('mimetype', 'like', '%jpg'),
                ('mimetype', 'like', '%png')])):
        for attachment in chunk.with_context(prefetch_fields=False).read(
                ['datas', 'mimetype']):
            res = env['ir.attachment']._make_thumbnail(attachment)
            if res.get('thumbnail'):
                env['ir.attachment'].browse(attachment['id']).write({
                    'thumbnail': res['thumbnail']})


def update_res_company_onboarding_company_state(env):
    # based on old base_onboarding_company_done
    good_companies = env["res.company"].search([]).filtered(lambda c: (
        c.partner_id.browse(
            c.partner_id.sudo().address_get(adr_pref=['contact'])['contact']
        ).sudo().street
    ))
    good_companies.write({'base_onboarding_company_state': 'done'})


def merge_duplicated_partner_banks(env):
    openupgrade.logged_query(
        env.cr, """
        SELECT id, key
        FROM (
            SELECT id, count(*) over (
               PARTITION BY company_id, sanitized_acc_number
               ORDER BY company_id, sanitized_acc_number) AS num,
               dense_rank() over (
               ORDER BY company_id, sanitized_acc_number) AS key
            FROM res_partner_bank
        ) t
        WHERE num > 1
        ORDER BY key, id"""
    )
    partner_banks = {}
    for partner_bank_id, key in env.cr.fetchall():
        partner_banks.setdefault(key, []).append(partner_bank_id)
    for key in partner_banks:
        openupgrade_merge_records.merge_records(
            env, 'res.partner.bank', partner_banks[key][1:],
            partner_banks[key][0], field_spec={'sequence': 'max', 'currency_id': 'max'}, method='sql',
            delete=True, exclude_columns=None, model_table='res_partner_bank')


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    env['ir.ui.menu']._parent_store_compute()
    env['res.partner.category']._parent_store_compute()
    generate_thumbnails(env)
    update_res_company_onboarding_company_state(env)
    openupgrade.load_data(
        env.cr, 'base', 'migrations/12.0.1.3/noupdate_changes.xml')
    # Activate back the noupdate flag on the group
    openupgrade.logged_query(
        env.cr, """
        UPDATE ir_model_data SET noupdate=True
        WHERE  module='base' AND name='group_user'""",
    )
    merge_duplicated_partner_banks(env)
