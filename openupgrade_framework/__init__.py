import logging
import os

from odoo.modules import get_module_path
from odoo.tools import config

from . import odoo_patch

if not config.get("upgrade_path"):
    path = get_module_path("openupgrade_scripts", display_warning=False)
    if path:
        logging.getLogger(__name__).info(
            "Setting upgrade_path to the scripts directory inside the module "
            "location of openupgrade_scripts"
        )
        config["upgrade_path"] = os.path.join(path, "scripts")
        path = get_module_path("enterprise_upgrade_scripts", display_warning=False)
        if path:
            logging.getLogger(__name__).info(
                "Setting upgrade_path to the scripts directory inside the module "
                "location of enterprise_upgrade_scripts"
            )
            config["upgrade_path"] = (
                config["upgrade_path"] + "," + os.path.join(path, "scripts")
            )
