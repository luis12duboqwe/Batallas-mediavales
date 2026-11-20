"""Prevent duplicate active privacy requests in support cases.

Revision ID: 0019_privacy_active_unique
Revises: 0018_spanish_only_language

No existing support case is modified. If active privacy duplicates already
exist, migration refuses to proceed so operators can resolve them manually.
"""

from alembic import op
import sqlalchemy as sa

revision = "0019_privacy_active_unique"
down_revision = "0018_spanish_only_language"
branch_labels = None
depends_on = None

INDEX_NAME = "uq_support_privacy_active_user_subject"
PRIVACY_PREDICATE = (
    "status IN ('open', 'in_progress') AND subject IN ("
    "'[PRIVACY] Solicitud de eliminación de cuenta', "
    "'[PRIVACY] Solicitud de corrección de datos', "
    "'[PRIVACY] Consulta sobre retención de datos', "
    "'[PRIVACY] Consulta sobre privacidad')"
)


def upgrade() -> None:
    # Avoid silently closing or merging personal-data requests. No DDL runs
    # before this check, making a blocked migration non-destructive.
    connection = op.get_bind()
    duplicate = connection.execute(
        sa.text(
            "SELECT requester_id, subject, COUNT(*) AS n FROM support_cases "
            f"WHERE {PRIVACY_PREDICATE} "
            "GROUP BY requester_id, subject HAVING COUNT(*) > 1 LIMIT 1"
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Existing duplicate active privacy requests must be resolved "
            "by authorized support staff before migration 0019."
        )

    op.create_index(
        INDEX_NAME,
        "support_cases",
        ["requester_id", "subject"],
        unique=True,
        sqlite_where=sa.text(PRIVACY_PREDICATE),
        postgresql_where=sa.text(PRIVACY_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="support_cases")
