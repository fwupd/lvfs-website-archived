"""

Revision ID: 8f394b9db1f0
Revises: 0e38974d7935
Create Date: 2018-12-06 12:05:44.766344

"""

# revision identifiers, used by Alembic.
revision = '8f394b9db1f0'
down_revision = '0e38974d7935'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import User

def upgrade():
    op.add_column('users', sa.Column('password_ts', sa.DateTime(), nullable=True))
    for u in db.session.query(User).all():
        u.password_ts = u.atime
    db.session.commit()

def downgrade():
    op.drop_column('users', 'password_ts')
