"""Index common meeting history sorts and lookups."""
from alembic import op

revision = "0002_meeting_search_indexes"
down_revision = "0001_meetings"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_meetings_updated_at", "meetings", ["updated_at"])
    op.create_index("ix_meetings_title", "meetings", ["title"])

def downgrade():
    op.drop_index("ix_meetings_title", table_name="meetings")
    op.drop_index("ix_meetings_updated_at", table_name="meetings")
