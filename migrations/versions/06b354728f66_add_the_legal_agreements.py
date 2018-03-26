"""

Revision ID: 06b354728f66
Revises: efcd3338922a
Create Date: 2018-04-03 20:54:01.631909

"""

# revision identifiers, used by Alembic.
revision = '06b354728f66'
down_revision = 'efcd3338922a'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('agreements',
    sa.Column('agreement_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('text', sa.Unicode(), nullable=True),
    sa.PrimaryKeyConstraint('agreement_id'),
    sa.UniqueConstraint('agreement_id'),
    mysql_character_set='utf8mb4'
    )
    op.add_column(u'users', sa.Column('agreement_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'users', 'agreements', ['agreement_id'], ['agreement_id'])

def downgrade():
    op.drop_constraint(None, 'users', type_='foreignkey')
    op.drop_column(u'users', 'agreement_id')
    op.drop_table('agreements')
