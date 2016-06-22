# -*- coding: utf-8 -*-
# © 2015 Eficent Business and IT Consulting Services S.L. -
# Jordi Ballester Alomar
# © 2015 Serpent Consulting Services Pvt. Ltd. - Sudhir Arya
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from openupgradelib import openupgrade

table_renames = [('crm_case_section', 'crm_team')]


@openupgrade.migrate()
def migrate(cr, version):
    openupgrade.rename_tables(cr, table_renames)
