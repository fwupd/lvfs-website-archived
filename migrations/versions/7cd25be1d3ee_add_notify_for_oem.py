"""

Revision ID: 7cd25be1d3ee
Revises: 44250e0a730e
Create Date: 2019-09-09 11:42:43.752086

"""

# revision identifiers, used by Alembic.
revision = '7cd25be1d3ee'
down_revision = '44250e0a730e'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('users', sa.Column('notify_promote', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('notify_upload_affiliate', sa.Boolean(), nullable=True))
    op.add_column('users', sa.Column('notify_upload_vendor', sa.Boolean(), nullable=True))

def downgrade():
    op.drop_column('users', 'notify_upload_vendor')
    op.drop_column('users', 'notify_upload_affiliate')
    op.drop_column('users', 'notify_promote')
