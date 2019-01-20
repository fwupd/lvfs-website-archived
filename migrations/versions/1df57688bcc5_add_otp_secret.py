"""

Revision ID: 1df57688bcc5
Revises: 5c0b692d11dc
Create Date: 2019-01-20 20:45:11.976160

"""

# revision identifiers, used by Alembic.
revision = '1df57688bcc5'
down_revision = '5c0b692d11dc'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import User
from app.hash import _otp_hash

def upgrade():
    op.add_column('users', sa.Column('otp_secret', sa.String(length=16), nullable=True))
    op.add_column('users', sa.Column('is_otp_enabled', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('is_otp_working', sa.Boolean(), nullable=True))
    for user in db.session.query(User).all():
        user.otp_secret = _otp_hash()
    db.session.commit()

def downgrade():
    op.drop_column('users', 'otp_secret')
    op.drop_column('users', 'is_otp_enabled')
    op.drop_column('users', 'is_otp_working')
