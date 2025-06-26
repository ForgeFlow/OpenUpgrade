# Copyright 2025 ForgeFlow S.L. (https://www.forgeflow.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version=None):
    openupgrade.drop_columns(
        env.cr,
        [
            ("product_template", "service_to_purchase")
        ],
    )
