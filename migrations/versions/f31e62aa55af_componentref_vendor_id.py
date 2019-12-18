"""

Revision ID: f31e62aa55af
Revises: 4014b50cab9d
Create Date: 2019-12-18 09:40:25.806253

"""

# revision identifiers, used by Alembic.
revision = 'f31e62aa55af'
down_revision = '4014b50cab9d'

from alembic import op
import sqlalchemy as sa

from lvfs import db
from lvfs.models import ComponentRef

def upgrade():
    op.add_column('component_refs', sa.Column('vendor_id_partner', sa.Integer(), nullable=False))
    for mdref in db.session.query(ComponentRef):
        mdref.vendor_id_partner = mdref.vendor_id
        mdref.vendor_id = mdref.md.fw.vendor.vendor_id
    db.session.commit()
    op.create_foreign_key(None, 'component_refs', 'vendors', ['vendor_id_partner'], ['vendor_id'])

def downgrade():
    op.drop_constraint(None, 'component_refs', type_='foreignkey')
    op.drop_column('component_refs', 'vendor_id_partner')
