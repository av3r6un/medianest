from .health import health
from .auth import auth
from .config import config
from .jobs import jobs
from .queue import queue


rts = (*health, *auth, *config, *jobs, *queue)
