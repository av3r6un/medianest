from aiohttp.web import RouteTableDef

from backend.app_keys import WORKER


queue = RouteTableDef()


@queue.get('/queue/status')
async def queue_status(req, session=None):
  return req.app[WORKER].status


@queue.post('/queue/pause')
async def pause_queue(req, session=None):
  return req.app[WORKER].pause()


@queue.post('/queue/resume')
async def resume_queue(req, session=None):
  return req.app[WORKER].resume()
