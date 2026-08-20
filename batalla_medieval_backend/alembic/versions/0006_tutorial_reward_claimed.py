"""persist tutorial reward claim state

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tutorial_reward_claimed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Previous tutorial_step values were client-controlled and could be skipped
    # arbitrarily. Recompute them from durable game state under the new service.
    op.execute(sa.text("UPDATE users SET tutorial_step = 0"))


def downgrade() -> None:
    op.drop_column("users", "tutorial_reward_claimed")
