"""

Revision ID: 9d0a1adc8aee
Revises: b638621daa16
Create Date: 2018-03-19 10:46:54.398788

"""

# revision identifiers, used by Alembic.
revision = '9d0a1adc8aee'
down_revision = 'b638621daa16'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_column('users', 'is_enabled')
    op.drop_column('users', 'is_locked')

def downgrade():
    op.add_column('users', sa.Column('is_locked', mysql.TINYINT(display_width=4), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_enabled', mysql.INTEGER(display_width=11), server_default=sa.text('0'), autoincrement=False, nullable=True))
