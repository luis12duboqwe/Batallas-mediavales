"""Expand Alembic revision storage before the pre-existing long revision 0014.

Revision ID: 0013b_expand_alembic_version
Revises: 0013_message_world_scope

PostgreSQL enforces Alembic's default VARCHAR(32) and cannot record the
historical 0014_achievement_progress_world_scope revision (37 characters).
Preserve historical revision IDs and widen the version table instead.
SQLite ignores VARCHAR width, so no DDL is necessary there.
"""

from alembic import op

revision = "0013b_expand_alembic_version"
down_revision = "0013_message_world_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE alembic_version "
            "ALTER COLUMN version_num TYPE VARCHAR(128)"
        )


def downgrade() -> None:
    # Never shrink the version table: prior/still-current revision identifiers
    # may exceed VARCHAR(32), making downgrade itself impossible.
    pass
