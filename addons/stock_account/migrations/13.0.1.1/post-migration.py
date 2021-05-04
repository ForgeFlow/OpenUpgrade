# Copyright 2020 ForgeFlow <http://www.forgeflow.com>
# Copyright 2020 Andrii Skrypka
# Copyright 2021 Tecnativa - Carlos Dauden
# Copyright 2021 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging

from openupgradelib import openupgrade
from odoo import _
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from odoo.addons.base.models.ir_model import query_insert

_logger = logging.getLogger(__name__)

# Declare global index hat will be used to set the svl ids
svl_id = 0
# Declare global variant to avoid that it is passed between methods
precision_price = 0


def _prepare_common_svl_vals(move, product):
    global svl_id
    svl_id += 1
    return {
        "id": svl_id,
        "create_uid": move["write_uid"],
        "create_date": move["date"],
        "write_uid": move["write_uid"],
        "write_date": move["date"],
        "stock_move_id": move["id"],
        "company_id": move["company_id"],
        "product_id": move["product_id"],
        "description": move["reference"] and "%s - %s" % (move["reference"], product.name) or product.name,
        "value": 0.0,
        "unit_cost": 0.0,
        "remaining_qty": 0.0,
        "remaining_value": 0.0,
        "quantity": 0.0,
        "old_product_price_history_id": None,
        "account_move_id": move["account_move_id"],
    }


def _prepare_in_svl_vals(move, quantity, unit_cost, product, is_dropship):
    vals = _prepare_common_svl_vals(move, product)
    vals.update({
        "value": float_round(unit_cost * quantity, precision_digits=precision_price),
        "unit_cost": unit_cost,
        "quantity": quantity,
    })
    if product.cost_method in ("average", "fifo") and not is_dropship:
        vals["remaining_qty"] = quantity
        vals["remaining_value"] = vals["value"]
    return vals


def _prepare_out_svl_vals(move, quantity, unit_cost, product):
    # Quantity is negative for out valuation layers.
    quantity = -quantity
    vals = _prepare_common_svl_vals(move, product)
    vals.update({
        "value": float_round(unit_cost * quantity, precision_digits=precision_price),
        "unit_cost": unit_cost,
        "quantity": quantity,
        "remaining_qty": 0.0,
        "remaining_value": 0.0,
    })
    return vals


def _prepare_svl_usage_vals(index, move, quantity, value):
    return {
        "create_uid": move["write_uid"],
        "create_date": move["date"],
        "write_uid": move["write_uid"],
        "write_date": move["date"],
        "stock_valuation_layer_id": index,
        "stock_move_id": move["id"],
        "quantity": quantity,
        "value": value,
        "company_id": move["company_id"],
        "product_id": move["product_id"],
    }


def create_table_stock_valuation_layer_usage(env):
    env.cr.execute("""
        CREATE TABLE stock_valuation_layer_usage (
            id serial NOT NULL,
            create_uid int4,
            create_date timestamp without time zone,
            write_date timestamp without time zone,
            write_uid int4,
            company_id int4,
            stock_valuation_layer_id int4,
            stock_move_id int4,
            product_id int4,
            quantity numeric,
            value numeric,
            primary key(id)
        )""")


def _prepare_man_svl_vals(price_history_rec, previous_price, quantity, company, product):
    diff = price_history_rec["cost"] - previous_price
    value = float_round(diff * quantity, precision_digits=precision_price)
    global svl_id
    svl_id += 1
    svl_vals = {
        "id": svl_id,
        "create_uid": price_history_rec["write_uid"],
        "create_date": price_history_rec["datetime"],
        "write_uid": price_history_rec["write_uid"],
        "write_date": price_history_rec["datetime"],
        "stock_move_id": None,
        "company_id": company.id,
        "product_id": product.id,
        "description": _("Product value manually modified (from %s to %s)"
                         ) % (previous_price, price_history_rec["cost"]),
        "value": value,
        "unit_cost": 0.0,
        "remaining_qty": 0.0,
        "remaining_value": 0.0,
        "quantity": 0.0,
        "old_product_price_history_id": price_history_rec["id"],
        "account_move_id": price_history_rec["account_move_id"],
    }
    return svl_vals


def get_product_price_history(env, company_id, product_id):
    env.cr.execute("""
        WITH account_move_rel AS (
            SELECT id, create_date
            FROM (
                SELECT id, create_date, COUNT(*) OVER(PARTITION BY create_date) AS qty
                FROM account_move
                WHERE stock_move_id IS NULL
            ) foo
            WHERE qty = 1
        )
        SELECT pph.id, pph.company_id, pph.product_id, pph.datetime, pph.cost, rel.id AS account_move_id,
            pph.create_uid, pph.create_date, pph.write_uid, pph.write_date
        FROM product_price_history pph
        LEFT JOIN account_move_rel rel ON rel.create_date = pph.create_date
        WHERE pph.company_id = %s AND pph.product_id = %s
        ORDER BY pph.datetime, pph.id
    """, (company_id, product_id))
    return env.cr.dictfetchall()


def get_stock_moves(env, company_id, product_id):
    env.cr.execute("""
        WITH account_move_rel AS (
            SELECT id, stock_move_id
            FROM (
                SELECT id, stock_move_id, COUNT(*) OVER(PARTITION BY stock_move_id) AS qty
                FROM account_move
                WHERE stock_move_id IS NOT NULL
            ) foo
            WHERE qty = 1
        )
        SELECT sm.id, sm.company_id, sm.product_id, sm.date, sm.product_qty, sm.reference,
            COALESCE(sm.price_unit, 0.0) AS price_unit, rel.id AS account_move_id,
            sm.create_uid, sm.create_date, sm.write_uid, sm.write_date,
            CASE WHEN (sl.usage <> 'internal' AND (sl.usage <> 'transit' OR sl.company_id <> sm.company_id))
                   AND (sld.usage = 'internal' OR (sld.usage = 'transit' AND sld.company_id = sm.company_id))
                   THEN 'in'
                 WHEN (sl.usage = 'internal' OR (sl.usage = 'transit' AND sl.company_id = sm.company_id))
                   AND (sld.usage <> 'internal' AND (sld.usage <> 'transit' OR sld.company_id <> sm.company_id))
                   THEN 'out'
                 WHEN sl.usage = 'supplier' AND sld.usage = 'customer' THEN 'dropship'
                 WHEN sl.usage = 'customer' AND sld.usage = 'supplier' THEN 'dropship_return'
                 ELSE 'other'
            END AS move_type,
            move_orig.move_orig_id, move_dest.move_dest_id
        FROM stock_move sm
        LEFT JOIN stock_location sl ON sl.id = sm.location_id
        LEFT JOIN stock_location sld ON sld.id = sm.location_dest_id
        LEFT JOIN account_move_rel rel ON rel.stock_move_id = sm.id
        LEFT JOIN stock_move_move_rel move_orig ON sm.id = move_orig.move_orig_id
        LEFT JOIN stock_move_move_rel move_dest ON sm.id = move_dest.move_dest_id
        WHERE sm.company_id = %s AND sm.product_id = %s AND state = 'done'
        ORDER BY sm.date, sm.id
    """, (company_id, product_id))
    return env.cr.dictfetchall()


@openupgrade.logging()
def generate_stock_valuation_layer(env):
    openupgrade.logged_query(
        env.cr, """
            ALTER TABLE stock_valuation_layer
            ADD COLUMN old_product_price_history_id integer""",
    )
    company_obj = env["res.company"]
    product_obj = env["product.product"]
    global svl_id
    # we assure we get last value of the table
    # just in case if the table is filled during the update
    env.cr.execute("SELECT id FROM stock_valuation_layer LIMIT 1")
    svl_id = (env.cr.fetchall() or [(svl_id, )])[0][0]
    # Needed to modify global variable
    global precision_price
    precision_price = env["decimal.precision"].precision_get("Product Price")
    precision_uom = env["decimal.precision"].precision_get(
        "Product Unit of Measure"
    )
    companies = company_obj.search([])
    products = product_obj.with_context(active_test=False).search([("type", "in", ("product", "consu"))])
    all_svl_list = []
    all_svl_usage_list = []
    usage = openupgrade.table_exists(env.cr, 'stock_valuation_layer_usage')
    for company in companies:
        _logger.info("Doing svl for company_id {}".format(company.id))
        for product in products:
            history_lines = []
            if product.cost_method != "fifo":
                history_lines = get_product_price_history(env, company.id, product.id)
            moves = get_stock_moves(env, company.id, product.id)
            svl_in_vals_list = []
            svl_in_vals_mto_list = []
            svl_out_vals_list = []
            svl_man_vals_list = []
            svl_usage_vals_list = []
            svl_in_index = 0
            h_index = 0
            previous_price = 0.0
            previous_qty = 0.0
            for move in moves:
                is_dropship = True if move["move_type"] in ("dropship", "dropship_return") else False
                if product.cost_method in ("average", "standard"):
                    # useless for Fifo because we have price unit in stock.move
                    # Add manual adjusts
                    have_qty = not float_is_zero(previous_qty, precision_digits=precision_uom)
                    while h_index < len(history_lines) and history_lines[h_index]["datetime"] < move["date"]:
                        price_history_rec = history_lines[h_index]
                        if float_compare(price_history_rec["cost"], previous_price, precision_digits=precision_price):
                            if have_qty:
                                svl_vals = _prepare_man_svl_vals(
                                    price_history_rec, previous_price, previous_qty, company, product)
                                svl_man_vals_list.append(svl_vals)
                            previous_price = price_history_rec["cost"]
                        h_index += 1
                # Add in svl for not mto
                if move["move_type"] == "in" or is_dropship:
                    total_qty = previous_qty + move["product_qty"]
                    # TODO: is needed vaccum if total_qty is negative?
                    if float_is_zero(total_qty, precision_digits=precision_uom):
                        previous_price = move["price_unit"]
                    else:
                        previous_price = float_round(
                            (previous_price * previous_qty + move["price_unit"] * move["product_qty"]) / total_qty,
                            precision_digits=precision_price)
                    svl_vals = _prepare_in_svl_vals(
                        move, move["product_qty"], move["price_unit"], product, is_dropship)
                    # Use separate list for the MTO case
                    if not move["move_dest_id"]:
                        svl_in_vals_list.append(svl_vals)
                    else:
                        svl_in_vals_mto_list.append(svl_vals)
                    previous_qty = total_qty
                # Add out svl with candidates
                svl_in_index_mto = 0  # This will be for the MTO
                if (move["move_type"] == "out" or is_dropship) and move["move_orig_id"]:
                    svl_in_vals_mto_filtered_list = [
                        item if item["move_dest_id"] == move["move_orig_id"] else None for item in svl_in_vals_mto_list
                    ]
                    qty = move["product_qty"]
                    if product.cost_method in ("average", "fifo") and not is_dropship:
                        # Reduce remaining qty in svl of type "in"
                        while qty > 0 and svl_in_index_mto < len(svl_in_vals_mto_filtered_list):
                            if svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"] >= qty:
                                candidate_cost = (svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_value"] /
                                                  svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"])
                                if usage:
                                    # Prepare layer usage
                                    svl_usage_vals = _prepare_svl_usage_vals(
                                        svl_in_vals_mto_filtered_list[svl_in_index_mto]["id"], move, qty,
                                        candidate_cost*qty)
                                    svl_usage_vals_list.append(svl_usage_vals)
                                svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"] -= qty
                                svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_value"] = float_round(
                                    candidate_cost * svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"],
                                    precision_digits=precision_price)
                                qty = 0
                            elif svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"]:
                                if usage:
                                    # Prepare layer usage
                                    svl_usage_vals = _prepare_svl_usage_vals(
                                        svl_in_vals_mto_filtered_list[svl_in_index_mto]["id"],
                                        move, svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"],
                                        svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_value"])
                                    svl_in_vals_mto_filtered_list.append(svl_usage_vals)
                                qty -= svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"]
                                svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_qty"] = 0.0
                                svl_in_vals_mto_filtered_list[svl_in_index_mto]["remaining_value"] = 0.0
                                svl_in_index_mto += 1
                            else:
                                svl_in_index_mto += 1
                    if product.cost_method == 'fifo':
                        svl_vals = _prepare_out_svl_vals(
                            move, move["product_qty"], abs(move["price_unit"]), product)
                    else:
                        svl_vals = _prepare_out_svl_vals(
                            move, move["product_qty"], previous_price, product)
                    svl_out_vals_list.append(svl_vals)
                    previous_qty -= move["product_qty"]
                # Add out svl with no candidates
                if (move["move_type"] == "out" or is_dropship) and not move["move_orig_id"]:
                    qty = move["product_qty"]
                    if product.cost_method in ("average", "fifo") and not is_dropship:
                        # Reduce remaining qty in svl of type "in"
                        while qty > 0 and svl_in_index < len(svl_in_vals_list):
                            if svl_in_vals_list[svl_in_index]["remaining_qty"] >= qty:
                                candidate_cost = (svl_in_vals_list[svl_in_index]["remaining_value"] /
                                                  svl_in_vals_list[svl_in_index]["remaining_qty"])
                                if usage:
                                    # Prepare layer usage
                                    svl_usage_vals = _prepare_svl_usage_vals(
                                        svl_in_vals_list[svl_in_index]["id"], move, qty, candidate_cost*qty)
                                    svl_usage_vals_list.append(svl_usage_vals)
                                svl_in_vals_list[svl_in_index]["remaining_qty"] -= qty
                                svl_in_vals_list[svl_in_index]["remaining_value"] = float_round(
                                    candidate_cost * svl_in_vals_list[svl_in_index]["remaining_qty"],
                                    precision_digits=precision_price)
                                qty = 0
                            elif svl_in_vals_list[svl_in_index]["remaining_qty"]:
                                if usage:
                                    # Prepare layer usage
                                    svl_usage_vals = _prepare_svl_usage_vals(
                                        svl_in_vals_list[svl_in_index]["id"],
                                        move, svl_in_vals_list[svl_in_index]["remaining_qty"],
                                        svl_in_vals_list[svl_in_index]["remaining_value"])
                                    svl_usage_vals_list.append(svl_usage_vals)
                                qty -= svl_in_vals_list[svl_in_index]["remaining_qty"]
                                svl_in_vals_list[svl_in_index]["remaining_qty"] = 0.0
                                svl_in_vals_list[svl_in_index]["remaining_value"] = 0.0
                                svl_in_index += 1
                            else:
                                svl_in_index += 1
                    if product.cost_method == 'fifo':
                        svl_vals = _prepare_out_svl_vals(
                            move, move["product_qty"], abs(move["price_unit"]), product)
                    else:
                        svl_vals = _prepare_out_svl_vals(
                            move, move["product_qty"], previous_price, product)
                    svl_out_vals_list.append(svl_vals)
                    previous_qty -= move["product_qty"]
            # Add manual adjusts after last move
            if product.cost_method in ("average", "standard") and not float_is_zero(
                    previous_qty, precision_digits=precision_uom):
                # useless for Fifo because we have price unit on product form
                while h_index < len(history_lines):
                    price_history_rec = history_lines[h_index]
                    if float_compare(price_history_rec["cost"], previous_price, precision_digits=precision_price):
                        svl_vals = _prepare_man_svl_vals(
                            price_history_rec, previous_price, previous_qty, company, product)
                        svl_man_vals_list.append(svl_vals)
                        previous_price = price_history_rec["cost"]
                    h_index += 1
            all_svl_list.extend(svl_in_vals_list + svl_out_vals_list + svl_man_vals_list)
            if usage:
                all_svl_usage_list.extend(svl_usage_vals_list)
    if all_svl_list:
        all_svl_list = sorted(all_svl_list, key=lambda k: (k["create_date"]))
        _logger.info("To create {} svl records".format(len(all_svl_list)))
        query_insert(env.cr, "stock_valuation_layer", all_svl_list)
    if all_svl_usage_list:
        all_svl_usage_list = sorted(all_svl_usage_list, key=lambda k: (k["create_date"]))
        _logger.info("To create {} svl usage records".format(len(all_svl_usage_list)))
        query_insert(env.cr, "stock_valuation_layer_usage", all_svl_usage_list)


@openupgrade.migrate()
def migrate(env, version):
    if not openupgrade.table_exists(env.cr, 'stock_valuation_layer_usage'):
        create_table_stock_valuation_layer_usage(env)
    generate_stock_valuation_layer(env)
    openupgrade.delete_records_safely_by_xml_id(
        env, [
            "stock_account.default_cost_method",
            "stock_account.default_valuation",
            "stock_account.property_stock_account_input_prd",
            "stock_account.property_stock_account_output_prd",
        ]
    )
    openupgrade.logged_query(env.cr, """
    SELECT setval('stock_valuation_layer_id_seq',
        (SELECT MAX(id) FROM stock_valuation_layer)+1)""")
    openupgrade.logged_query(env.cr, """
    SELECT setval('stock_valuation_layer_usage_id_seq',
        (SELECT MAX(id) FROM stock_valuation_layer_usage)+1)""")
