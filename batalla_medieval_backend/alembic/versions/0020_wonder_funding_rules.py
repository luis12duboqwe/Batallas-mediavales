"""Versioned alliance wonder financing, keeping existing worlds on legacy-v1.

Revision ID: 0020_wonder_funding
Revises: 0019_privacy_active_unique
"""

from alembic import op
import sqlalchemy as sa

revision = "0020_wonder_funding"
down_revision = "0019_privacy_active_unique"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("worlds") as batch:
        batch.add_column(
            sa.Column("wonder_rules_version", sa.String(24), nullable=False, server_default="legacy-v1")
        )
    op.create_table(
        "wonder_funding",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("world_id", sa.Integer, sa.ForeignKey("worlds.id"), nullable=False),
        sa.Column("city_id", sa.Integer, sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("alliance_id", sa.Integer, sa.ForeignKey("alliances.id"), nullable=False),
        sa.Column("target_level", sa.Integer, nullable=False),
        sa.Column("funded_wood", sa.Integer, nullable=False, server_default="0"),
        sa.Column("funded_stone", sa.Integer, nullable=False, server_default="0"),
        sa.Column("funded_iron", sa.Integer, nullable=False, server_default="0"),
        sa.Column("funded_gold", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="funding"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint("target_level BETWEEN 1 AND 100", name="ck_wonder_funding_level"),
        sa.CheckConstraint(
            "funded_wood >= 0 AND funded_stone >= 0 AND funded_iron >= 0 AND funded_gold >= 0",
            name="ck_wonder_funding_nonnegative",
        ),
        sa.UniqueConstraint("city_id", "target_level", "owner_id", "alliance_id", name="uq_wonder_funding_project"),
    )
    op.create_index("ix_wonder_funding_world_id", "wonder_funding", ["world_id"])
    op.create_index("ix_wonder_funding_city_id", "wonder_funding", ["city_id"])
    op.create_table(
        "wonder_contributions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("world_id", sa.Integer, sa.ForeignKey("worlds.id"), nullable=False),
        sa.Column("funding_id", sa.Integer, sa.ForeignKey("wonder_funding.id"), nullable=False),
        sa.Column("contributor_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("source_city_id", sa.Integer, sa.ForeignKey("cities.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("wood", sa.Integer, nullable=False, server_default="0"),
        sa.Column("stone", sa.Integer, nullable=False, server_default="0"),
        sa.Column("iron", sa.Integer, nullable=False, server_default="0"),
        sa.Column("gold", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "wood >= 0 AND stone >= 0 AND iron >= 0 AND gold >= 0 "
            "AND (wood + stone + iron + gold) > 0",
            name="ck_wonder_contrib_positive",
        ),
        sa.UniqueConstraint("world_id", "contributor_id", "idempotency_key", name="uq_wonder_contrib_request"),
    )


def downgrade():
    op.drop_table("wonder_contributions")
    op.drop_index("ix_wonder_funding_city_id", table_name="wonder_funding")
    op.drop_index("ix_wonder_funding_world_id", table_name="wonder_funding")
    op.drop_table("wonder_funding")
    with op.batch_alter_table("worlds") as batch:
        batch.drop_column("wonder_rules_version")
