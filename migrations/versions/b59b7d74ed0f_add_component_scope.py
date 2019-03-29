"""

Revision ID: b59b7d74ed0f
Revises: b73c19797ab0
Create Date: 2019-03-28 22:20:34.726745

"""

# revision identifiers, used by Alembic.
revision = 'b59b7d74ed0f'
down_revision = '5eaa6ae92bb7'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Component, Scope
from app.util import _fix_component_name

def upgrade():

    if 1:
        op.create_table('scopes',
        sa.Column('scope_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('scope_id'),
        sa.UniqueConstraint('scope_id'),
        mysql_character_set='utf8mb4'
        )
        op.add_column('components', sa.Column('scope_id', sa.Integer(), nullable=True))
        op.create_foreign_key('components_ibfk_3', 'components', 'scopes', ['scope_id'], ['scope_id'])

    if 1:
        db.session.add(Scope(value='unknown', name='Unknown'))
        db.session.add(Scope(value='system', name='System Firmware'))
        db.session.add(Scope(value='device', name='Device Firmware'))
        db.session.add(Scope(value='ec', name='EC Firmware'))
        db.session.add(Scope(value='me', name='ME Firmware'))

    # convert the existing components
    apxs = {}
    for sco in db.session.query(Scope).all():
        apxs[sco.value] = sco
    for md in db.session.query(Component).all():

        # already set
        if md.scope_id:
            continue

        # find suffix
        for apx_value in apxs:
            sco = apxs[apx_value]
            for suffix in ['System Update', 'System Firmware', 'BIOS']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.scope_id = apxs['system'].scope_id
                    break
            for suffix in ['Embedded Controller Firmware']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.scope_id = apxs['ec'].scope_id
                    break
            for suffix in ['ME Firmware']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.scope_id = apxs['me'].scope_id
                    break

        # protocol fallback
        if not md.scope_id:
            if md.protocol and md.protocol.value in ['org.flashrom', 'org.uefi.capsule', 'org.uefi.capsule']:
                md.scope_id = apxs['system'].scope_id
            else:
                md.scope_id = apxs['device'].scope_id

        # fix component name
        name_new = _fix_component_name(md.name, md.developer_name_display)
        if md.name != name_new:
            print('Fixing %s->%s' % (md.name, name_new))
            md.name = name_new
        else:
            print('Ignoring %s' % md.name)

    # all done
    db.session.commit()

def downgrade():
    op.drop_constraint('components_ibfk_3', 'components', type_='foreignkey')
    op.drop_column('components', 'scope_id')
    op.drop_table('scopes')
