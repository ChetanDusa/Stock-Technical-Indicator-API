"""Create accounts with hashed API keys and a validated subscription tier."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("subscription", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "subscription IN ('free', 'pro', 'premium')", name="ck_users_subscription"
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("api_key_hash", name="uq_users_api_key_hash"),
    )


def downgrade():
    op.drop_table("users")
