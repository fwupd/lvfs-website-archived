"""

Revision ID: bf6316b24565
Revises: 6e1c3e4cfe3c
Create Date: 2020-04-22 15:16:59.941379

"""

# revision identifiers, used by Alembic.
revision = 'bf6316b24565'
down_revision = '6e1c3e4cfe3c'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('firmware', sa.Column('vendor_odm_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_firmware_vendor_odm_id'), 'firmware', ['vendor_odm_id'], unique=False)
    op.create_foreign_key(None, 'firmware', 'vendors', ['vendor_odm_id'], ['vendor_id'])


def downgrade():
    op.drop_constraint(None, 'firmware', type_='foreignkey')
    op.drop_index(op.f('ix_firmware_vendor_odm_id'), table_name='firmware')
    op.drop_column('firmware', 'vendor_odm_id')
