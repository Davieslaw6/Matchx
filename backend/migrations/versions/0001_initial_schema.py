"""Initial schema for private single-owner MATCH X."""
from alembic import op
from app.models import Base

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # The initial revision uses the single canonical metadata definition. Future revisions
    # must use explicit Alembic operations and must not mutate existing historical revisions.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=False)

def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=False)
