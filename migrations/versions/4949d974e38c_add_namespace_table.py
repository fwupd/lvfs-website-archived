"""

Revision ID: 9373c9ac33da
Revises: 2307f4ebe8c1
Create Date: 2019-09-02 20:07:24.876043

"""

# revision identifiers, used by Alembic.
revision = '9373c9ac33da'
down_revision = '814ccd8a065b'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('namespaces',
    sa.Column('namespace_id', sa.Integer(), nullable=False),
    sa.Column('vendor_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('ctime', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ),
    sa.PrimaryKeyConstraint('namespace_id'),
    sa.UniqueConstraint('namespace_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_foreign_key('namespace_ibfk_3', 'namespaces', 'users', ['user_id'], ['user_id'])

def downgrade():
    op.drop_table('namespaces')
