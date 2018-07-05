"""

Revision ID: b797e21e0536
Revises: 6f0522f34435
Create Date: 2018-07-05 19:17:16.134134

"""

# revision identifiers, used by Alembic.
revision = 'b797e21e0536'
down_revision = '6f0522f34435'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import User

def upgrade():
    op.add_column('users', sa.Column('is_approved_public', sa.Boolean(), nullable=True))
    for u in db.session.query(User).all():
        if u.is_qa:
            u.is_approved_public = True
    db.session.commit()

def downgrade():
    op.drop_column('users', 'is_approved_public')
