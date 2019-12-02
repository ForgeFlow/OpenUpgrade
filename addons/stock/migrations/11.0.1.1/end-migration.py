# Copyright 2018 Tecnativa - Pedro M. Baeza
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
import logging

from odoo.exceptions import ValidationError
from openupgradelib import openupgrade, openupgrade_merge_records

QUANT_MERGE_OPS = {
    # The rest of the values are good with default merge operation
    'in_date': 'min',
    'removal_date': 'max',
}


def merge_quants(env):
    logger = logging.getLogger('openupgrade.stock.end_migration')
    group_list = [
        'product_id', 'package_id', 'lot_id', 'location_id', 'owner_id',
    ]
    StockQuant = env['stock.quant']
    groups = StockQuant.read_group([], group_list, group_list, lazy=False)
    for group in groups:
        quants = StockQuant.search(group['__domain'])
        if len(quants) == 1:
            continue
        openupgrade_merge_records.merge_records(
            env.with_context(skip_reference_refs_orm=True),
            'stock.quant', quants[1:].ids, quants[0].id, QUANT_MERGE_OPS,
        )


@openupgrade.migrate(use_env=True)
def migrate(env, version):
    merge_quants(env)
