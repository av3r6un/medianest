from aiohttp.web import RouteTableDef

from backend.app_keys import WORKER
from backend.services import JobService


jobs = RouteTableDef()


@jobs.post('/jobs')
async def create_job(req, session):
  payload = await req.json()
  payload['source_user_agent'] = req.headers.get('User-Agent')
  return await JobService.create(session, payload)


@jobs.post('/jobs:dry-run')
async def dry_run_job(req, session=None):
  payload = await req.json()
  payload['source_user_agent'] = req.headers.get('User-Agent')
  return await JobService.dry_run(payload)


@jobs.get('/jobs')
async def list_jobs(req, session):
  state = req.query.get('state')
  return await JobService.all(session, state)


@jobs.get('/jobs/{uid}')
async def get_job(req, session):
  uid = req.match_info.get('uid')
  return await JobService.get(session, uid)


@jobs.get('/jobs/{uid}/events')
async def get_job_events(req, session):
  uid = req.match_info.get('uid')
  return await JobService.events(session, uid)


@jobs.patch('/jobs/{uid}')
async def update_job(req, session):
  uid = req.match_info.get('uid')
  payload = await req.json()
  return await JobService.update(session, uid, payload)


@jobs.post('/jobs/{uid}/cancel')
async def cancel_job(req, session):
  uid = req.match_info.get('uid')
  return await JobService.cancel(session, uid, req.app.get(WORKER))


@jobs.post('/jobs/{uid}/retry')
async def retry_job(req, session):
  uid = req.match_info.get('uid')
  payload = await req.json() if req.can_read_body else {}
  return await JobService.retry(session, uid, payload)
