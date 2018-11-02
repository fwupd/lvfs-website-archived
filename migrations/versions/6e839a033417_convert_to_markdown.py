"""

Revision ID: 6e839a033417
Revises: 3fd6598319ec
Create Date: 2018-11-02 10:46:24.049386

"""

# revision identifiers, used by Alembic.
revision = '6e839a033417'
down_revision = '3fd6598319ec'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Component
from app.util import _markdown_from_xml

def upgrade():
    # convert from AppStream to Markdown
    for md in db.session.query(Component).all():
        if md.description.startswith('<'):
            tmp = _markdown_from_xml(md.description)
            #print('convert ' + md.description + ' to ' + tmp)
            md.description = tmp
        if md.release_description and md.release_description.startswith('<'):
            tmp = _markdown_from_xml(md.release_description)
            tmp = tmp.replace('WARNING : ', '')
            tmp = tmp.replace('CHANGES IN THIS RELEASE\n', '')
            tmp = tmp.replace('\n[Problem fixes]\n\n * Nothing.', '')
            tmp = tmp.replace('\n[New functions or enhancements]\n\n * Nothing', '')
            tmp = tmp.replace('[Problem fixes]\n\n * Nothing', '')
            tmp = tmp.replace('[Problem fixes]',
                              'This update fixes the following problems:')
            tmp = tmp.replace('[New functions or enhancements]',
                              'This update also adds the following features:')
            tmp = tmp.replace('[Problem fixes]',
                              'This update fixes the following problems:')
            tmp = tmp.replace('[Important updates]',
                              'This update fixes the following important problems:')
            tmp = tmp.replace(' * - ', ' * ')
            tmp = tmp.replace('  ', ' ')
            tmp = tmp.replace('\n.\n', '\n\n')
            tmp = tmp.replace('\n\n\n', '\n\n')
            tmp = tmp.strip()
            #print('\n\nconvert ' + str(md.component_id) + '\n' + md.release_description + '\n..to..\n' + tmp)
            md.release_description = tmp
    db.session.commit()

def downgrade():
    pass
