from aiohttp.web import Application, run_app
from dotenv import load_dotenv
from .app_keys import DB_SESSIONMAKER, WORKER
from .config import Settings
import asyncio
import logging
import sys
import os


if sys.platform == 'win32':
  load_dotenv('.env')
  
settings = Settings()

LOG_FILENAME = 'logs/all.log' if sys.platform == 'win32' else '/var/log/alloha/all.log'

async def db_ctx(app: Application):
  from .utils.engine import session_maker, dispose

  app[DB_SESSIONMAKER] = session_maker
  yield
  await dispose()

async def worker_ctx(app: Application):
  from .services import WorkerService

  worker = WorkerService(app[DB_SESSIONMAKER])
  app[WORKER] = worker
  task = None
  if settings.WORKER_ENABLED:
    task = asyncio.create_task(worker.run())
  yield
  if task:
    await worker.stop()
    await task
  
def create_app():
  from .routes import rts
  from .utils import middlewares
  
  app = Application(middlewares=middlewares, client_max_size=settings.REQUEST_MAX_BYTES)
  if LOG_FILENAME:
    os.makedirs(os.path.dirname(LOG_FILENAME), exist_ok=True)
  logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] WEB: %(message)s",
    datefmt="%Y-%d-%m %H:%M:%S",
    filename=LOG_FILENAME
  )
  app.add_routes(rts)
  app.cleanup_ctx.append(db_ctx)
  app.cleanup_ctx.append(worker_ctx)
  if os.getenv('DEBUG', False):
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logging.getLogger().addHandler(console)
  
  return app

def start():
  run_app(
    create_app(),
    host=settings.APP_HOST,
    port=settings.APP_PORT,
    access_log_format='%{X-Forwarded-For}i %s - "%r" (%b | %D) %{User-Agent}i',
  )
