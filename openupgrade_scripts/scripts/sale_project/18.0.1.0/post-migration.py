# Copyright 2025 Le Filament (https://le-filament.com)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade, openupgrade_180


def _convert_company_dependent(env):
    openupgrade_180.convert_company_dependent(
        env,
        "product.template",
        "project_id",
        old_field_id=openupgrade.get_legacy_name("project_id"),
    )
    openupgrade_180.convert_company_dependent(
        env,
        "product.template",
        "project_template_id",
        old_field_id=openupgrade.get_legacy_name("project_template_id"),
    )


@openupgrade.migrate()
def migrate(env, version):
    _convert_company_dependent(env)

    old_field = env.ref("product.field_res_partner__property_product_pricelist")
    openupgrade_180.convert_company_dependent(
        env,
        "res.partner",
        "specific_property_product_pricelist",
        old_field_id=old_field.id,
    )
