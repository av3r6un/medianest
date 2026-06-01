from typing import Any

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


DB_SESSIONMAKER = web.AppKey('db_sessionmaker', async_sessionmaker[AsyncSession])
WORKER = web.AppKey('worker', Any)
