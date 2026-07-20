"""Revision: hybrid free data sources schema."""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "44174ab49f28"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "api_quota_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("calls_made", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "source", name="uq_quota_date_source"),
    )
    op.create_index("ix_api_quota_logs_date", "api_quota_logs", ["date"])
    op.create_index("ix_api_quota_logs_source", "api_quota_logs", ["source"])

    with op.batch_alter_table("countries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column("football_data_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("worldcup26_id", sa.String(length=20), nullable=True))
        batch_op.create_index("ix_countries_football_data_id", ["football_data_id"], unique=True)
        batch_op.create_index("ix_countries_worldcup26_id", ["worldcup26_id"], unique=True)

    with op.batch_alter_table("fixtures", schema=None) as batch_op:
        batch_op.add_column(sa.Column("football_data_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("worldcup26_id", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("api_football_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("group_name", sa.String(length=4), nullable=True))
        batch_op.create_index("ix_fixtures_football_data_id", ["football_data_id"], unique=True)
        batch_op.create_index("ix_fixtures_worldcup26_id", ["worldcup26_id"], unique=True)
        batch_op.create_index("ix_fixtures_api_football_id", ["api_football_id"], unique=True)

    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_football_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("football_data_team_id", sa.Integer(), nullable=True))
        batch_op.drop_column("sportmonks_team_id")
        batch_op.create_index("ix_players_api_football_id", ["api_football_id"], unique=True)


def downgrade():
    with op.batch_alter_table("players", schema=None) as batch_op:
        batch_op.drop_index("ix_players_api_football_id")
        batch_op.add_column(sa.Column("sportmonks_team_id", sa.Integer(), nullable=True))
        batch_op.drop_column("football_data_team_id")
        batch_op.drop_column("api_football_id")

    with op.batch_alter_table("fixtures", schema=None) as batch_op:
        batch_op.drop_index("ix_fixtures_api_football_id")
        batch_op.drop_index("ix_fixtures_worldcup26_id")
        batch_op.drop_index("ix_fixtures_football_data_id")
        batch_op.drop_column("group_name")
        batch_op.drop_column("api_football_id")
        batch_op.drop_column("worldcup26_id")
        batch_op.drop_column("football_data_id")

    with op.batch_alter_table("countries", schema=None) as batch_op:
        batch_op.drop_index("ix_countries_worldcup26_id")
        batch_op.drop_index("ix_countries_football_data_id")
        batch_op.drop_column("worldcup26_id")
        batch_op.drop_column("football_data_id")
        batch_op.drop_column("code")

    op.drop_index("ix_api_quota_logs_source", "api_quota_logs")
    op.drop_index("ix_api_quota_logs_date", "api_quota_logs")
    op.drop_table("api_quota_logs")
