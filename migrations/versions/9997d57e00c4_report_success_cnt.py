"""

Revision ID: 9997d57e00c4
Revises: c30479270168
Create Date: 2019-04-11 16:37:32.382777

"""

# revision identifiers, used by Alembic.
revision = '9997d57e00c4'
down_revision = 'c30479270168'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.add_column('firmware', sa.Column('report_failure_cnt', sa.Integer(), nullable=True))
    op.add_column('firmware', sa.Column('report_issue_cnt', sa.Integer(), nullable=True))
    op.add_column('firmware', sa.Column('report_success_cnt', sa.Integer(), nullable=True))

def downgrade():
    op.drop_column('firmware', 'report_success_cnt')
    op.drop_column('firmware', 'report_issue_cnt')
    op.drop_column('firmware', 'report_failure_cnt')
