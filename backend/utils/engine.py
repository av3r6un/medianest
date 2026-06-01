from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import os

db_url = os.getenv('DB_URL')

engine = create_async_engine(db_url, echo=False, pool_recycle=200, pool_pre_ping=True)

session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

async def dispose():
  await engine.dispose()
