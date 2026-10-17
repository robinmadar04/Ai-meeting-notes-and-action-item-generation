"""Create meeting and action item tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001_meetings"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("meetings",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("title", sa.String(240), nullable=False),
        sa.Column("meeting_date", sa.Date(), nullable=True), sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("key_points", sa.JSON(), nullable=False),
        sa.Column("decisions", sa.JSON(), nullable=False), sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_meetings_created_at", "meetings", ["created_at"])
    op.create_table("action_items",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("meeting_id", sa.Integer(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False), sa.Column("owner", sa.String(200), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True), sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["meetings.id"], ondelete="CASCADE"))
    op.create_index("ix_action_items_meeting_id", "action_items", ["meeting_id"])

def downgrade():
    op.drop_index("ix_action_items_meeting_id", table_name="action_items")
    op.drop_table("action_items")
    op.drop_index("ix_meetings_created_at", table_name="meetings")
    op.drop_table("meetings")
