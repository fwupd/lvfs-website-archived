"""

Revision ID: 2fe8c6bfedb7
Revises: c3d10b2a239c
Create Date: 2019-01-12 18:32:32.512449

"""

# revision identifiers, used by Alembic.
revision = '2fe8c6bfedb7'
down_revision = 'c3d10b2a239c'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

def upgrade():
    op.create_table('tests',
    sa.Column('test_id', sa.Integer(), nullable=False),
    sa.Column('firmware_id', sa.Integer(), nullable=False),
    sa.Column('plugin_id', sa.Text(), nullable=True),
    sa.Column('waivable', sa.Boolean(), nullable=True),
    sa.Column('started_ts', sa.DateTime(), nullable=True),
    sa.Column('ended_ts', sa.DateTime(), nullable=True),
    sa.Column('waived_ts', sa.DateTime(), nullable=True),
    sa.Column('waived_user_id', sa.Integer(), nullable=True),
    sa.Column('max_age', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['firmware_id'], ['firmware.firmware_id'], ),
    sa.ForeignKeyConstraint(['waived_user_id'], ['users.user_id'], ),
    sa.PrimaryKeyConstraint('test_id'),
    sa.UniqueConstraint('test_id'),
    mysql_character_set='utf8mb4'
    )
    op.create_table('test_attributes',
    sa.Column('test_attribute_id', sa.Integer(), nullable=False),
    sa.Column('test_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('message', sa.Text(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['test_id'], ['tests.test_id'], ),
    sa.PrimaryKeyConstraint('test_attribute_id'),
    sa.UniqueConstraint('test_attribute_id'),
    mysql_character_set='utf8mb4'
    )
    op.drop_index('assay_attribute_id', table_name='assay_attributes')
    op.drop_table('assay_attributes')
    op.drop_index('assay_id', table_name='assays')
    op.drop_table('assays')

def downgrade():
    op.create_table('assays',
    sa.Column('assay_id', mysql.INTEGER(display_width=11), autoincrement=True, nullable=False),
    sa.Column('component_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.Column('plugin_id', mysql.TEXT(), nullable=True),
    sa.Column('waivable', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True),
    sa.Column('started_ts', mysql.DATETIME(), nullable=True),
    sa.Column('ended_ts', mysql.DATETIME(), nullable=True),
    sa.Column('waived_ts', mysql.DATETIME(), nullable=True),
    sa.Column('waived_user_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=True),
    sa.CheckConstraint(u'`waivable` in (0,1)', name=u'CONSTRAINT_1'),
    sa.ForeignKeyConstraint(['component_id'], [u'components.component_id'], name=u'assays_ibfk_1'),
    sa.ForeignKeyConstraint(['waived_user_id'], [u'users.user_id'], name=u'assays_ibfk_2'),
    sa.PrimaryKeyConstraint('assay_id'),
    mysql_default_charset=u'utf8mb4',
    mysql_engine=u'InnoDB'
    )
    op.create_index('assay_id', 'assays', ['assay_id'], unique=True)
    op.create_table('assay_attributes',
    sa.Column('assay_attribute_id', mysql.INTEGER(display_width=11), autoincrement=True, nullable=False),
    sa.Column('assay_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.Column('title', mysql.TEXT(), nullable=False),
    sa.Column('message', mysql.TEXT(), nullable=True),
    sa.Column('success', mysql.TINYINT(display_width=1), autoincrement=False, nullable=True),
    sa.CheckConstraint(u'`success` in (0,1)', name=u'CONSTRAINT_1'),
    sa.ForeignKeyConstraint(['assay_id'], [u'assays.assay_id'], name=u'assay_attributes_ibfk_1'),
    sa.PrimaryKeyConstraint('assay_attribute_id'),
    mysql_default_charset=u'utf8mb4',
    mysql_engine=u'InnoDB'
    )
    op.create_index('assay_attribute_id', 'assay_attributes', ['assay_attribute_id'], unique=True)
    op.drop_table('test_attributes')
    op.drop_table('tests')
