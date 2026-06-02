from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

db_url = os.getenv('DB_URL')

engine_kwargs = dict(echo=False, pool_recycle=200)
if not str(db_url or '').startswith('mysql+aiomysql://'):
  engine_kwargs['pool_pre_ping'] = True

engine = create_async_engine(db_url, **engine_kwargs)

session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def dispose():
  await engine.dispose()
