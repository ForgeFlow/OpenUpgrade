# Copyright 2019 Eficent <http://www.eficent.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from openupgradelib import openupgrade
from psycopg2.extensions import AsIs


def fill_mrp_workcenter_resource_calendar_id(cr):
    openupgrade.logged_query(
        cr, """
        UPDATE mrp_workcenter mw
        SET resource_calendar_id = rr.calendar_id
        FROM resource_resource rr
        WHERE mw.resource_id = rr.id AND mw.resource_calendar_id IS NULL
        """
    )


def fill_mrp_workcenter_productivity_loss_loss_id(cr):
    openupgrade.logged_query(
        cr, """
        UPDATE mrp_workcenter_productivity_loss wpl
        SET loss_id = wplt.id
        FROM mrp_workcenter_productivity_loss_type wplt
        WHERE wpl.loss_id IS NULL AND wpl.%s = wplt.loss_type
        """, (AsIs(openupgrade.get_legacy_name('loss_type')), ),
    )


def fill_stock_warehouse_picking_types(env):
    warehouse_ids = env['stock.warehouse'].search([])
    for warehouse_id in warehouse_ids:
        warehouse_id._create_or_update_sequences_and_picking_types()


@openupgrade.migrate()
def migrate(env, version):
    cr = env.cr
    fill_mrp_workcenter_resource_calendar_id(cr)
    openupgrade.load_data(
        cr, 'mrp', 'migrations/12.0.2.0/noupdate_changes.xml')
    fill_mrp_workcenter_productivity_loss_loss_id(cr)
    fill_stock_warehouse_picking_types(env)
