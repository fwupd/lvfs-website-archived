"""

Revision ID: 6dde8aa078e5
Revises: 5bcdefe58b44
Create Date: 2018-12-12 12:46:55.097606

"""

# revision identifiers, used by Alembic.
revision = '6dde8aa078e5'
down_revision = '3a261eab059c'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from app import db
from app.models import Component, Protocol

def upgrade():
    if 1:
        op.create_table('protocol',
        sa.Column('protocol_id', sa.Integer(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('is_signed', sa.Boolean(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=True),
        sa.Column('can_verify', sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint('protocol_id'),
        sa.UniqueConstraint('protocol_id'),
        mysql_character_set='utf8mb4'
        )
        op.add_column('components', sa.Column('protocol_id', sa.Integer(), nullable=True))
        op.create_foreign_key('components_ibfk_2', 'components', 'protocol', ['protocol_id'], ['protocol_id'])

    # add the protocols we understand now
    if 1:
        db.session.add(Protocol(value='unknown',
                                name='Unknown or unsupported custom format',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.hughski.colorhug',
                                name='Hughski ColorHug',
                                can_verify=True,
                                is_signed=False))
        db.session.add(Protocol(value='org.altusmetrum.altos',
                                name='AltOS Update',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.qualcomm.dfu',
                                name='Qualcomm (Cambridge Silicon Radio) DFU',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.dell.dock',
                                name='Dell Dock',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.synaptics.mst',
                                name='Synaptics MST',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='org.usb.dfu',
                                name='USB Device Firmware Update (DFU 1.0 and 1.1)',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.st.dfuse',
                                name='STMicroelectronics DfuSe',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.8bitdo',
                                name='8bitdo',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.google.fastboot',
                                name='Fastboot',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='org.flashrom',
                                name='Flashrom',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='org.nvmexpress',
                                name='NVMe',
                                can_verify=False,
                                is_signed=False)) # FIXME?
        db.session.add(Protocol(value='org.dmtf.redfish',
                                name='Redfish',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.realtek.rts54',
                                name='Realtek RTS54',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.acme.test',
                                name='Test protocol DO NOT USE',
                                can_verify=True,
                                is_public=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.intel.thunderbolt',
                                name='Intel Thunderbolt',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='org.uefi.capsule',
                                name='UEFI UpdateCapsule',
                                can_verify=True,
                                is_signed=True))
        db.session.add(Protocol(value='com.logitech.unifying',
                                name='Logitech Unifying',
                                can_verify=False,
                                is_signed=False))
        db.session.add(Protocol(value='com.logitech.unifyingsigned',
                                name='Logitech Unifying (Signed)',
                                can_verify=False,
                                is_signed=True))
        db.session.add(Protocol(value='com.wacom.usb',
                                name='Wacom (USB devices)',
                                can_verify=False,
                                is_signed=False)) # FIXME?
        db.session.commit()

    # find the IDs for each value
    proto_id_for_value = {}
    for pr in db.session.query(Protocol).all():
        proto_id_for_value[pr.value] = pr.protocol_id

    # convert the existing components
    for md in db.session.query(Component).all():
        if md.appstream_id.startswith('com.lenovo.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.hughski.ColorHug.') or \
             md.appstream_id.startswith('com.hughski.ColorHugALS.') or \
             md.appstream_id.startswith('com.hughski.ColorHug2.'):
            md.protocol_id = proto_id_for_value['com.hughski.colorhug']
        elif md.appstream_id.startswith('com.intel.thunderbolt.'):
            md.protocol_id = proto_id_for_value['com.intel.thunderbolt']
        elif md.appstream_id.startswith('com.intel.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.Quanta.uefi'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.logitech.'):
            md.protocol_id = proto_id_for_value['com.logitech.unifying']
        elif md.appstream_id.startswith('TI.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('org.linaro.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.fsoft.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.hp.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.dell.uefi'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        elif md.appstream_id.startswith('com.dell.tbt'):
            md.protocol_id = proto_id_for_value['com.intel.thunderbolt']
        elif md.appstream_id.startswith('com.akitio.'):
            md.protocol_id = proto_id_for_value['com.intel.thunderbolt']
        elif md.appstream_id.startswith('com.nitrokey.'):
            md.protocol_id = proto_id_for_value['org.usb.dfu']
        elif md.appstream_id.startswith('com.8bitdo.'):
            md.protocol_id = proto_id_for_value['com.8bitdo']
        elif md.appstream_id.startswith('com.altusmetrum.'):
            md.protocol_id = proto_id_for_value['org.altusmetrum.altos']
        elif md.appstream_id.startswith('com.AIAIAI.'):
            md.protocol_id = proto_id_for_value['com.qualcomm.dfu']
        elif md.appstream_id.startswith('com.acme.'):
            md.protocol_id = proto_id_for_value['org.usb.dfu']
        elif md.appstream_id.startswith('fakedevice'):
            md.protocol_id = proto_id_for_value['org.usb.dfu']
        elif md.appstream_id.startswith('com.jabra.'):
            md.protocol_id = proto_id_for_value['org.usb.dfu']
        elif md.appstream_id.startswith('com.dell.mst'):
            md.protocol_id = proto_id_for_value['com.synaptics.mst']
        elif md.appstream_id.startswith('com.tw.supermicro.'):
            md.protocol_id = proto_id_for_value['org.uefi.capsule']
        else:
            print(('unknown protocol for', md.appstream_id))
            md.protocol_id = proto_id_for_value['unknown']
    db.session.commit()

def downgrade():
    op.drop_constraint('components_ibfk_2', 'components', type_='foreignkey')
    op.drop_column('components', 'protocol_id')
    op.drop_table('protocol')
