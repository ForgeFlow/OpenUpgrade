from openupgradelib import openupgrade


def _convert_project_task_assigned_users(env):
    openupgrade.m2o_to_x2m(
        env.cr,
        env["project.task"],
        "project_task",
        "user_ids",
        openupgrade.get_legacy_name("user_id"),
    )


def _add_followers_to_project_for_allowed_internal_users(env):
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO mail_followers (res_model, res_id, partner_id)
        SELECT 'project.project', prj_user_rel.project_project_id, users.partner_id
        FROM project_allowed_internal_users_rel prj_user_rel
        JOIN res_users users ON users.id = prj_user_rel.res_users_id
        JOIN project_project prj
            ON prj.id = prj_user_rel.project_project_id
            AND prj.privacy_visibility = 'followers'
        ON CONFLICT DO NOTHING
        """,
    )


def _add_followers_to_project_for_allowed_portal_users(env):
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO mail_followers (res_model, res_id, partner_id)
        SELECT 'project.project', prj_user_rel.project_project_id, users.partner_id
        FROM project_allowed_portal_users_rel prj_user_rel
        JOIN res_users users ON users.id = prj_user_rel.res_users_id
        JOIN project_project prj
            ON prj.id = prj_user_rel.project_project_id
            AND prj.privacy_visibility = 'portal'
        ON CONFLICT DO NOTHING
        """,
    )


def _add_followers_to_task_for_allowed_users(env):
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO mail_followers (res_model, res_id, partner_id)
        SELECT 'project.task', task_user_rel.project_task_id, users.partner_id
        FROM project_task_res_users_rel task_user_rel
        JOIN res_users users ON users.id = task_user_rel.res_users_id
        ON CONFLICT DO NOTHING
        """,
    )


def _fill_project_task_display_project_id(env):
    # Example: 1 task A with 1 subtask B in project P
    # A -> project_id=P, display_project_id=P
    # B -> project_id=P (to inherit from ACL/security rules), display_project_id=False
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE project_task task
        SET display_project_id = task.project_id
        WHERE task.parent_id IS NULL
        """,
    )

def _fill_project_project_stage(env):
    # use data from analytic_account_stage
    env.cr.execute("""
        alter table account_analytic_account drop constraint if exists account_analytic_account_stage_id_fkey;
        """)
    env.cr.execute("""
        UPDATE project_project_stage SET active = false;
        INSERT INTO project_project_stage
        (create_date, write_date, sequence, name, fold, create_uid, write_uid, active)
        SELECT create_date, write_date, sequence, name, fold, create_uid, write_uid, true
        FROM analytic_account_stage;
        """)
    env.cr.execute("""
        WITH BQ AS(
            SELECT pps.id as pps_id, aas.id as aas_id from project_project_stage pps
            INNER JOIN analytic_account_stage aas on aas.name = pps.name
            WHERE pps.name = aas.name
            )
        UPDATE account_analytic_account aaa
        SET stage_id = (
        SELECT BQ.pps_id
        FROM account_analytic_account aaa2
        JOIN BQ ON BQ.aas_id = aaa2.stage_id
        AND aaa.id = aaa2.id);
        """)


@openupgrade.migrate()
def migrate(env, version):
    _convert_project_task_assigned_users(env)
    _add_followers_to_project_for_allowed_internal_users(env)
    _add_followers_to_project_for_allowed_portal_users(env)
    _add_followers_to_task_for_allowed_users(env)
    _fill_project_task_display_project_id(env)
    openupgrade.load_data(env.cr, "project", "15.0.1.2/noupdate_changes.xml")
    openupgrade.delete_record_translations(
        env.cr,
        "project",
        [
            "mail_template_data_project_task",
            "rating_project_request_email_template",
        ],
    )
    _fill_project_project_stage(env)
