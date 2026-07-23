"""Widen fixtures.group_name for values like FINAL.

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("fixtures") as batch_op:
        batch_op.alter_column(
            "group_name",
            existing_type=sa.String(length=4),
            type_=sa.String(length=32),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("fixtures") as batch_op:
        batch_op.alter_column(
            "group_name",
            existing_type=sa.String(length=32),
            type_=sa.String(length=4),
            existing_nullable=True,
        )
