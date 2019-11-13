"""

Revision ID: 9b46ff543492
Revises: 05217bb7d0c0
Create Date: 2019-11-13 14:06:41.553762

"""

# revision identifiers, used by Alembic.
revision = '9b46ff543492'
down_revision = '13c307a09ff1'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('component_refs',
    sa.Column('component_ref_id', sa.Integer(), nullable=False),
    sa.Column('component_id', sa.Integer(), nullable=True),
    sa.Column('vendor_id', sa.Integer(), nullable=False),
    sa.Column('protocol_id', sa.Integer(), nullable=True),
    sa.Column('appstream_id', sa.Text(), nullable=True),
    sa.Column('version', sa.Text(), nullable=False),
    sa.Column('release_tag', sa.Text(), nullable=True),
    sa.Column('date', sa.DateTime(), nullable=True),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('url', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['component_id'], ['components.component_id'], ),
    sa.ForeignKeyConstraint(['protocol_id'], ['protocol.protocol_id'], ),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.vendor_id'], ),
    sa.PrimaryKeyConstraint('component_ref_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_index(op.f('ix_component_refs_component_ref_id'), 'component_refs', ['component_ref_id'], unique=True)

def downgrade():
    op.drop_index(op.f('ix_component_refs_component_ref_id'), table_name='component_refs')
    op.drop_table('component_refs')
