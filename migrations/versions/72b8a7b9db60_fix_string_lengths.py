"""

Revision ID: 72b8a7b9db60
Revises: None
Create Date: 2018-03-15 16:15:09.186747

"""

# revision identifiers, used by Alembic.
revision = '72b8a7b9db60'
down_revision = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.alter_column('components', 'appstream_id',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('components', 'filename_contents',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('components', 'version',
               existing_type=mysql.VARCHAR(length=255),
               nullable=False)
    op.alter_column('conditions', 'key',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('conditions', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('firmware_events', 'target',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('guids', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('keywords', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('report_attributes', 'key',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('requirements', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('restrictions', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)
    op.alter_column('search_events', 'value',
               existing_type=mysql.TEXT(),
               nullable=False)

def downgrade():
    op.alter_column('search_events', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('restrictions', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('requirements', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('report_attributes', 'key',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('keywords', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('guids', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('firmware_events', 'target',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('conditions', 'value',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('conditions', 'key',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('components', 'version',
               existing_type=mysql.VARCHAR(length=255),
               nullable=True)
    op.alter_column('components', 'filename_contents',
               existing_type=mysql.TEXT(),
               nullable=True)
    op.alter_column('components', 'appstream_id',
               existing_type=mysql.TEXT(),
               nullable=True)
