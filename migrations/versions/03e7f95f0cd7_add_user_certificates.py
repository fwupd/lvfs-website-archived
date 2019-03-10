"""

Revision ID: 03e7f95f0cd7
Revises: 7c281751c3ec
Create Date: 2019-03-10 11:19:32.382473

"""

# revision identifiers, used by Alembic.
revision = '03e7f95f0cd7'
down_revision = 'b298782e35cb'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('certificates',
    sa.Column('certificate_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('ctime', sa.DateTime(), nullable=False),
    sa.Column('serial', sa.String(length=40), nullable=False),
    sa.Column('text', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('certificate_id'),
    sa.UniqueConstraint('certificate_id'),
    mysql_character_set='utf8mb4'
    )

def downgrade():
    op.drop_table('certificates')
