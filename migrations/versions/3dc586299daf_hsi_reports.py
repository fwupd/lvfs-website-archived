"""

Revision ID: 3dc586299daf
Revises: 0956dab5aa94
Create Date: 2020-05-19 12:57:06.200229

"""

# revision identifiers, used by Alembic.
revision = '3dc586299daf'
down_revision = '0956dab5aa94'

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table('hsi_reports',
    sa.Column('hsi_report_id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('signature', sa.Text(), nullable=True),
    sa.Column('machine_id', sa.String(length=64), nullable=False),
    sa.Column('distro', sa.Text(), nullable=True),
    sa.Column('kernel_cmdline', sa.Text(), nullable=True),
    sa.Column('kernel_version', sa.Text(), nullable=True),
    sa.Column('host_product', sa.Text(), nullable=True),
    sa.Column('host_vendor', sa.Text(), nullable=True),
    sa.Column('host_family', sa.Text(), nullable=True),
    sa.Column('host_sku', sa.Text(), nullable=True),
    sa.Column('host_security_id', sa.Text(), nullable=False),
    sa.Column('host_security_version', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('hsi_report_id')
    )
    op.create_index(op.f('ix_hsi_reports_host_family'), 'hsi_reports', ['host_family'], unique=False)
    op.create_index(op.f('ix_hsi_reports_host_sku'), 'hsi_reports', ['host_sku'], unique=False)
    op.create_index(op.f('ix_hsi_reports_host_product'), 'hsi_reports', ['host_product'], unique=False)
    op.create_index(op.f('ix_hsi_reports_host_vendor'), 'hsi_reports', ['host_vendor'], unique=False)
    op.create_table('hsi_report_attrs',
    sa.Column('report_attr_id', sa.Integer(), nullable=False),
    sa.Column('hsi_report_id', sa.Integer(), nullable=False),
    sa.Column('appstream_id', sa.Text(), nullable=False),
    sa.Column('hsi_result', sa.Text(), nullable=True),
    sa.Column('is_success', sa.Boolean(), nullable=True),
    sa.Column('is_runtime', sa.Boolean(), nullable=True),
    sa.Column('is_obsoleted', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['hsi_report_id'], ['hsi_reports.hsi_report_id'], ),
    sa.PrimaryKeyConstraint('report_attr_id')
    )
    op.create_index(op.f('ix_hsi_report_attrs_hsi_report_id'), 'hsi_report_attrs', ['hsi_report_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_hsi_report_attrs_hsi_report_id'), table_name='hsi_report_attrs')
    op.drop_table('hsi_report_attrs')
    op.drop_index(op.f('ix_hsi_reports_host_vendor'), table_name='hsi_reports')
    op.drop_index(op.f('ix_hsi_reports_host_product'), table_name='hsi_reports')
    op.drop_index(op.f('ix_hsi_reports_host_family'), table_name='hsi_reports')
    op.drop_index(op.f('ix_hsi_reports_host_sku'), table_name='hsi_reports')
    op.drop_table('hsi_reports')
