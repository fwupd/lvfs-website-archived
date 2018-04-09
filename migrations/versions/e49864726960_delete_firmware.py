"""

Revision ID: e49864726960
Revises: 06b354728f66
Create Date: 2018-04-09 12:00:57.797059

"""

# revision identifiers, used by Alembic.
revision = 'e49864726960'
down_revision = '06b354728f66'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    from app import db
    from app.models import Remote, Vendor
    db.session.add(Remote(name='deleted', is_public=False))
    db.session.commit()

def downgrade():
    pass
