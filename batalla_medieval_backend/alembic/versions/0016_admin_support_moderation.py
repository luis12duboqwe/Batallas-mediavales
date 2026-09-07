"""Add BM-0073 administration, support and moderation fields.

Revision ID: 0016_admin_support_moderation
Revises: 0015_world_lifecycle
"""

from alembic import op
import sqlalchemy as sa

revision = "0016_admin_support_moderation"
down_revision = "0015_world_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("admin_role", sa.String(length=16), nullable=True))

    with op.batch_alter_table("logs") as batch_op:
        batch_op.add_column(sa.Column("target_type", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("target_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("before_state", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("after_state", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reversible", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("reversed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("reversed_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("support_case_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_logs_reversed_by_id_users", "users", ["reversed_by_id"], ["id"])
        batch_op.create_index("ix_logs_target_type", ["target_type"], unique=False)
        batch_op.create_index("ix_logs_target_id", ["target_id"], unique=False)
        batch_op.create_index("ix_logs_support_case_id", ["support_case_id"], unique=False)

    op.create_table(
        "support_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("world_id", sa.Integer(), sa.ForeignKey("worlds.id"), nullable=True),
        sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("priority", sa.String(length=16), nullable=False, server_default="normal"),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_support_cases_requester_id", "support_cases", ["requester_id"])
    op.create_index("ix_support_cases_world_id", "support_cases", ["world_id"])
    op.create_index("ix_support_cases_assigned_to_id", "support_cases", ["assigned_to_id"])
    op.create_index("ix_support_cases_status", "support_cases", ["status"])
    op.create_index("ix_support_cases_priority", "support_cases", ["priority"])

    with op.batch_alter_table("logs") as batch_op:
        batch_op.create_foreign_key(
            "fk_logs_support_case_id_support_cases",
            "support_cases",
            ["support_case_id"],
            ["id"],
        )

    for table_name in ("chat_messages", "forum_posts"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()))
            batch_op.add_column(sa.Column("moderation_reason", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("moderated_by_id", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("moderated_at", sa.DateTime(), nullable=True))
            batch_op.create_foreign_key(
                f"fk_{table_name}_moderated_by_id_users",
                "users",
                ["moderated_by_id"],
                ["id"],
            )


def downgrade() -> None:
    for table_name in ("forum_posts", "chat_messages"):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(f"fk_{table_name}_moderated_by_id_users", type_="foreignkey")
            batch_op.drop_column("moderated_at")
            batch_op.drop_column("moderated_by_id")
            batch_op.drop_column("moderation_reason")
            batch_op.drop_column("is_hidden")

    with op.batch_alter_table("logs") as batch_op:
        batch_op.drop_constraint("fk_logs_support_case_id_support_cases", type_="foreignkey")

    op.drop_index("ix_support_cases_priority", table_name="support_cases")
    op.drop_index("ix_support_cases_status", table_name="support_cases")
    op.drop_index("ix_support_cases_assigned_to_id", table_name="support_cases")
    op.drop_index("ix_support_cases_world_id", table_name="support_cases")
    op.drop_index("ix_support_cases_requester_id", table_name="support_cases")
    op.drop_table("support_cases")

    with op.batch_alter_table("logs") as batch_op:
        batch_op.drop_index("ix_logs_support_case_id")
        batch_op.drop_index("ix_logs_target_id")
        batch_op.drop_index("ix_logs_target_type")
        batch_op.drop_constraint("fk_logs_reversed_by_id_users", type_="foreignkey")
        batch_op.drop_column("support_case_id")
        batch_op.drop_column("reversed_by_id")
        batch_op.drop_column("reversed_at")
        batch_op.drop_column("reversible")
        batch_op.drop_column("after_state")
        batch_op.drop_column("before_state")
        batch_op.drop_column("reason")
        batch_op.drop_column("target_id")
        batch_op.drop_column("target_type")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("admin_role")
