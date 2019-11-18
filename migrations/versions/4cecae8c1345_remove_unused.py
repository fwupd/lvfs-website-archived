"""

Revision ID: 4cecae8c1345
Revises: 2411ea0a8bf9
Create Date: 2019-11-18 13:24:23.940905

"""

# revision identifiers, used by Alembic.
revision = '4cecae8c1345'
down_revision = '2411ea0a8bf9'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.drop_column('components', 'version_format')
    op.drop_column('users', 'notify_upload_vendor')
    op.drop_column('users', 'is_vendor_manager')
    op.drop_column('users', 'is_analyst')
    op.drop_column('users', 'is_admin')
    op.drop_column('users', 'notify_demote_failures')
    op.drop_column('users', 'is_researcher')
    op.drop_column('users', 'notify_promote')
    op.drop_column('users', 'is_approved_public')
    op.drop_column('users', 'notify_server_error')
    op.drop_column('users', 'is_qa')
    op.drop_column('users', 'is_robot')
    op.drop_column('users', 'notify_upload_affiliate')
    op.drop_column('vendors', 'version_format')


def downgrade():
    op.add_column('vendors', sa.Column('version_format', mysql.VARCHAR(length=10), nullable=True))
    op.add_column('users', sa.Column('notify_upload_affiliate', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_robot', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_qa', mysql.INTEGER(display_width=11), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('notify_server_error', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_approved_public', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('notify_promote', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_researcher', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('notify_demote_failures', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_admin', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_analyst', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('is_vendor_manager', mysql.TINYINT(display_width=1), server_default=sa.text('0'), autoincrement=False, nullable=True))
    op.add_column('users', sa.Column('notify_upload_vendor', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True))
    op.add_column('components', sa.Column('version_format', mysql.VARCHAR(length=10), nullable=True))
