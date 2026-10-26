"""initial schema: songs, jobs, packs, sections_state

Revision ID: 0001
Revises:
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op

from api.models import UTCDateTime

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "songs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("expires_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_songs_sha256", "songs", ["sha256"])
    op.create_index("ix_songs_expires_at", "songs", ["expires_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "song_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
        sa.Column("started_at", UTCDateTime(), nullable=True),
        sa.Column("finished_at", UTCDateTime(), nullable=True),
    )
    op.create_index("ix_jobs_song_id", "jobs", ["song_id"])

    op.create_table(
        "packs",
        sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        sa.Column(
            "song_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", sa.String(64), nullable=True),
        sa.Column("destination", sa.String(16), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("created_at", UTCDateTime(), nullable=False),
    )
    op.create_index("ix_packs_song_id", "packs", ["song_id"])
    op.create_index("ix_packs_job_id", "packs", ["job_id"])

    op.create_table(
        "sections_state",
        sa.Column(
            "song_id",
            sa.Uuid(as_uuid=False),
            sa.ForeignKey("songs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("edited", sa.Boolean(), nullable=False),
        sa.Column("updated_at", UTCDateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("sections_state")
    op.drop_index("ix_packs_job_id", table_name="packs")
    op.drop_index("ix_packs_song_id", table_name="packs")
    op.drop_table("packs")
    op.drop_index("ix_jobs_song_id", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_songs_expires_at", table_name="songs")
    op.drop_index("ix_songs_sha256", table_name="songs")
    op.drop_table("songs")
