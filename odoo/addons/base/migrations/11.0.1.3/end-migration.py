# Copyright 2017 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade
from openupgradelib import openupgrade_merge_records


def merge_duplicated_partners(env):
    openupgrade_merge_records.merge_records(
        env, "res.partner", [77900], 16208,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [17526], 18397,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [18232], 18231,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [91135], 84211,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [91149], 147,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [48389], 18182,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [49013], 18573,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [79167], 12434,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [144377], 145121,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [18669], 18667,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [17832], 82751,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [93722], 58079,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    openupgrade_merge_records.merge_records(
        env, "res.partner", [144647], 101520,
        field_spec={"partner_latitude": 'max', "partner_longitude": "max"},
        method='sql', delete=False,
        exclude_columns=None, model_table="res_partner")
    partners = env["res.partner"].browse(
        [77900, 17526, 18232, 91135, 91149, 48389, 49013,
         79167, 144377, 18669, 17832, 93722, 144647]).exists()
    if partners:
        partners.unlink()
    # openupgrade.logged_query(
    #     env.cr, """
    #     UPDATE res_partner
    #     SET active = FALSE
    #     WHERE id IN (77900, 17526, 18232, 91135, 91149, 48389,
    #         49013, 79167, 144377, 18669, 17832, 93722, 144647)""")


@openupgrade.migrate()
def migrate(env, version):
    merge_duplicated_partners(env)
    openupgrade.disable_invalid_filters(env)
