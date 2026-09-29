"""Normalize production language preference to Spanish for BM-0083.

Revision ID: 0018_spanish_only_language
Revises: 0017_anticheat_review_metadata
"""

from alembic import op

revision = "0018_spanish_only_language"
down_revision = "0017_anticheat_review_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # BM-0083 removes incomplete English from production. Normalize every
    # non-canonical persisted value, including legacy case variants such as
    # `ES`/`Es`, so auth responses expose the single supported code.
    op.execute("UPDATE users SET language = 'es' WHERE language IS NULL OR language <> 'es'")


def downgrade() -> None:
    # Previous per-user preferences cannot be reconstructed safely. Keeping
    # Spanish is lossless for account data and avoids inventing a language.
    pass
