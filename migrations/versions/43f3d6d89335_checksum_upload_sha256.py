"""

Revision ID: 43f3d6d89335
Revises: f31e62aa55af
Create Date: 2020-01-05 15:19:32.960925

"""

# revision identifiers, used by Alembic.
revision = '43f3d6d89335'
down_revision = 'f31e62aa55af'

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('firmware', sa.Column('checksum_upload_sha256', sa.String(length=64), nullable=False))
    op.alter_column('firmware', 'checksum_upload', existing_type=sa.String(40), new_column_name='checksum_upload_sha1')
    op.alter_column('firmware', 'checksum_signed', existing_type=sa.String(40), new_column_name='checksum_signed_sha1')
    op.alter_column('firmware', 'checksum_pulp', existing_type=sa.String(64), new_column_name='checksum_signed_sha256')

def downgrade():
    op.drop_column('firmware', 'checksum_upload_sha256')
    op.alter_column('firmware', 'checksum_upload_sha1', existing_type=sa.String(40), new_column_name='checksum_upload')
    op.alter_column('firmware', 'checksum_signed_sha1', existing_type=sa.String(40), new_column_name='checksum_signed')
    op.alter_column('firmware', 'checksum_signed_sha256', existing_type=sa.String(64), new_column_name='checksum_pulp')
