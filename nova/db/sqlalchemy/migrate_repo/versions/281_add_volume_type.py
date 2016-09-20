from sqlalchemy import Column
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table


def upgrade(engine):
    """Function adds volume_type field."""
    meta = MetaData(bind=engine)
    bdms = Table('block_device_mapping', meta, autoload=True)
    shadow_bdms = Table('shadow_block_device_mapping', meta, autoload=True)
    volume_type = Column('volume_type', String(36), nullable=True)
    if not hasattr(bdms.c, 'volume_type'):
        bdms.create_column(volume_type)
    if not hasattr(shadow_bdms.c, 'volume_type'):
        shadow_bdms.create_column(volume_type.copy())
