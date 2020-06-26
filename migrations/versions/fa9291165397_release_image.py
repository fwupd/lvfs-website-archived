"""

Revision ID: fa9291165397
Revises: 13fe98071e44
Create Date: 2020-06-26 16:08:00.380099

"""

# revision identifiers, used by Alembic.
revision = 'fa9291165397'
down_revision = '13fe98071e44'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('components', sa.Column('release_image', sa.Text(), nullable=True))
    op.add_column('components', sa.Column('release_image_safe', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('components', 'release_image_safe')
    op.drop_column('components', 'release_image')
