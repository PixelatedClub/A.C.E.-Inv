"""Azure SQL adapter for the existing transactional beta domain service."""
import sqlite3
import struct

from .store import Store


class Record(dict):
    def __getitem__(self,key):
        return list(self.values())[key] if isinstance(key,int) else super().__getitem__(key)


class Result:
    def __init__(self,result):self.result=result
    def fetchone(self):
        row=self.result.mappings().fetchone()
        return Record(row) if row is not None else None
    def __iter__(self):return (Record(row) for row in self.result.mappings())


class Connection:
    def __init__(self,engine):self.connection=engine.connect()
    def __enter__(self):return self
    def __exit__(self,kind,value,trace):
        if kind:self.connection.rollback()
        else:self.connection.commit()
    def close(self):self.connection.close()
    def execute(self,sql,args=()):
        from sqlalchemy import text
        from sqlalchemy.exc import IntegrityError
        if sql=='BEGIN':
            self.connection.execute(text("""DECLARE @result int;
                EXEC @result=sp_getapplock @Resource='ACE.SharedSave', @LockMode='Shared',
                @LockOwner='Transaction', @LockTimeout=15000;
                IF @result < 0 THROW 51000, 'Inventory lock timeout', 1;"""))
            return None
        if sql=='BEGIN IMMEDIATE':
            self.connection.execute(text("""DECLARE @result int;
                EXEC @result=sp_getapplock @Resource='ACE.SharedSave', @LockMode='Exclusive',
                @LockOwner='Transaction', @LockTimeout=15000;
                IF @result < 0 THROW 51000, 'Inventory lock timeout', 1;"""))
            return None
        sql=sql.replace('substr(time,1,10)','SUBSTRING(time,1,10)')
        parts=sql.split('?')
        if len(parts)-1!=len(args):raise ValueError('SQL parameter count mismatch')
        statement=parts[0]+''.join(f':p{i}'+part for i,part in enumerate(parts[1:]))
        try:
            return Result(self.connection.execute(text(statement),{f'p{i}':value for i,value in enumerate(args)}))
        except IntegrityError as exc:
            raise sqlite3.IntegrityError('Database constraint rejected the request') from exc


class SQLStore(Store):
    def __init__(self,engine):self.engine=engine
    def connect(self):return Connection(self.engine)
    def backup(self,destination):
        raise RuntimeError('Azure SQL recovery is managed by the hosting platform; use its point-in-time restore.')

    def initialize_schema(self):
        from sqlalchemy import MetaData,Table,Column,Integer,Unicode,UnicodeText,ForeignKey,UniqueConstraint,CheckConstraint,Identity
        m=MetaData()
        def ident():return Column('id',Integer,Identity(),primary_key=True)
        def string(name,n=200,**kwargs):return Column(name,Unicode(n,collation='Latin1_General_100_CI_AS'),nullable=False,**kwargs)
        meta=Table('beta_meta',m,Column('id',Integer,primary_key=True,autoincrement=False),Column('revision',Integer,nullable=False))
        Table('items',m,ident(),string('name'),string('category'),string('size'),string('wings'),
              Column('total',Integer,nullable=False),string('status',20,server_default='active'),UniqueConstraint('name','category','size'),CheckConstraint('total>=0'))
        Table('cadets',m,ident(),string('name'),string('email',unique=True))
        Table('fittings',m,Column('cadet',Integer,ForeignKey('cadets.id'),primary_key=True),
              Column('category',Unicode(200,collation='Latin1_General_100_CI_AS'),primary_key=True),string('size'))
        Table('issues',m,ident(),Column('cadet',Integer,ForeignKey('cadets.id'),nullable=False),
              Column('item',Integer,ForeignKey('items.id'),nullable=False),Column('quantity',Integer,nullable=False),
              string('state',20),string('due',10,server_default=''),CheckConstraint('quantity>0'),
              CheckConstraint("state IN ('checkout','loan','returned','acquired','purchased')"))
        Table('audit',m,Column('revision',Integer,primary_key=True,autoincrement=False),string('time',50),string('actor'),string('action',40),
              string('operation',100,unique=True),Column('before_json',UnicodeText,nullable=False),Column('after_json',UnicodeText,nullable=False))
        Table('receipts',m,Column('operation',Unicode(100),primary_key=True),string('actor'),string('digest',64),Column('response',UnicodeText,nullable=False))
        Table('legacy_barcodes',m,Column('item',Integer,ForeignKey('items.id'),primary_key=True,autoincrement=False),string('barcode',unique=True))
        Table('legacy_archive',m,Column('table_name',Unicode(100),primary_key=True),Column('row_number',Integer,primary_key=True),Column('payload',UnicodeText,nullable=False))
        m.create_all(self.engine)
        with self.engine.begin() as c:
            if c.execute(meta.select()).first() is None:c.execute(meta.insert().values(id=1,revision=0))


def azure_engine(connection_string):
    from sqlalchemy import create_engine,event
    from sqlalchemy.engine import URL
    from azure.identity import DefaultAzureCredential
    if any(key in connection_string.casefold() for key in ('pwd=','password=','uid=','authentication=')):
        raise ValueError('Use managed identity, not credentials in the SQL connection string.')
    if 'encrypt=yes' not in connection_string.casefold() or 'trustservercertificate=no' not in connection_string.casefold():
        raise ValueError('Azure SQL requires Encrypt=yes and TrustServerCertificate=no.')
    engine=create_engine(URL.create('mssql+pyodbc',query={'odbc_connect':connection_string}),pool_pre_ping=True)
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=True)
    @event.listens_for(engine,'do_connect')
    def authenticate(dialect,record,args,params):
        args[0]=args[0].replace(';Trusted_Connection=Yes','')
        token=credential.get_token('https://database.windows.net/.default').token.encode('utf-16-le')
        params['attrs_before']={1256:struct.pack(f'<I{len(token)}s',len(token),token)}
    return engine
