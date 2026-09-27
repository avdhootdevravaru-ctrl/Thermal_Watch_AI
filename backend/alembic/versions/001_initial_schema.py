"""initial_schema

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-27 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.db.base import Base
    import app.db.models
    Base.metadata.create_all(op.get_bind())

def downgrade() -> None:
    from app.db.base import Base
    import app.db.models
    Base.metadata.drop_all(op.get_bind())
