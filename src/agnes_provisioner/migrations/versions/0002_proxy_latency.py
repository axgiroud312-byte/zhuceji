"""Persist the most recent proxy health-check latency without replacing pool data."""

import sqlalchemy as sa
from alembic import op

from agnes_provisioner.models import ProxyMeta

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "proxy_meta" not in inspector.get_table_names():
        ProxyMeta.__table__.create(bind=bind)
    elif "latency_ms" not in {column["name"] for column in inspector.get_columns("proxy_meta")}:
        # 0001 creates current model metadata on a fresh install, so the column
        # can already exist. Existing installations only need this nullable ADD.
        op.add_column("proxy_meta", sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "proxy_meta" in inspector.get_table_names() and "latency_ms" in {
        column["name"] for column in inspector.get_columns("proxy_meta")
    }:
        op.drop_column("proxy_meta", "latency_ms")
