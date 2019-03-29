"""

Revision ID: b59b7d74ed0f
Revises: b73c19797ab0
Create Date: 2019-03-28 22:20:34.726745

"""

# revision identifiers, used by Alembic.
revision = 'b59b7d74ed0f'
down_revision = '65b618b6e525'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Component, Category
from app.util import _fix_component_name

def upgrade():

    if 1:
        op.create_table('categories',
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('fallbacks', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('category_id'),
        sa.UniqueConstraint('category_id'),
        mysql_character_set='utf8mb4'
        )
        op.add_column('components', sa.Column('category_id', sa.Integer(), nullable=True))
        op.create_foreign_key('components_ibfk_3', 'components', 'categories', ['category_id'], ['category_id'])
        db.session.commit()

    if 1:
        #db.session.add(Category(value='', name='Unknown'))
        db.session.add(Category(value='X-System', name='System Update'))
        db.session.add(Category(value='X-Device', name='Device Update'))
        db.session.add(Category(value='X-EmbeddedController', name='Embedded Controller Update'))
        db.session.add(Category(value='X-ManagementEngine', name='Management Engine Update'))
        db.session.add(Category(value='X-Controller', name='Controller Update'))
        db.session.commit()

    # convert the existing components
    apxs = {}
    for cat in db.session.query(Category).all():
        apxs[cat.value] = cat
    for md in db.session.query(Component).all():

        # already set
        if md.category_id:
            continue

        # find suffix
        for apx_value in apxs:
            cat = apxs[apx_value]
            for suffix in ['System Update', 'System Firmware', 'BIOS']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.category_id = apxs['X-System'].category_id
                    break
            for suffix in ['Embedded Controller', 'Embedded controller']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.category_id = apxs['X-System'].category_id
                    break
            for suffix in ['ME Firmware']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.category_id = apxs['X-ManagementEngine'].category_id
                    break
            for suffix in ['controller Update']:
                if md.name.endswith(suffix) or md.summary.endswith(suffix):
                    md.category_id = apxs['controller'].category_id
                    break

        # protocol fallback
        if not md.category_id:
            if md.protocol and md.protocol.value in ['org.flashrom', 'org.uefi.capsule', 'org.uefi.capsule']:
                md.category_id = apxs['X-System'].category_id
            else:
                md.category_id = apxs['X-Device'].category_id

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
    op.drop_column('components', 'category_id')
    op.drop_table('categories')
