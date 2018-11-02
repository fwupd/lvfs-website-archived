"""

Revision ID: b1851318108b
Revises: 6e839a033417
Create Date: 2018-11-02 14:37:41.357640

"""

# revision identifiers, used by Alembic.
revision = 'b1851318108b'
down_revision = '6e839a033417'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Component

def upgrade():
    for md in db.session.query(Component).all():
        if md.screenshot_caption and md.screenshot_caption.startswith('<'):
            tmp = md.screenshot_caption
            tmp = tmp.replace('<p>', '')
            tmp = tmp.replace('</p>', '')
            md.screenshot_caption = tmp
    db.session.commit()

def downgrade():
    pass
