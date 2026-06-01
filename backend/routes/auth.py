from aiohttp.web import RouteTableDef

from backend.services import AuthService


auth = RouteTableDef()


@auth.post('/auth/login')
async def login(req, session):
  payload = await req.json()
  return await AuthService.login(session, payload)


@auth.post('/auth/refresh')
async def refresh(req, session):
  payload = await req.json()
  return await AuthService.refresh(session, payload)


@auth.post('/auth/logout')
async def logout(req, session):
  payload = await req.json() if req.can_read_body else {}
  return await AuthService.logout(session, req['current_user'], payload)


@auth.post('/auth/restore-password')
async def restore_password(req, session):
  payload = await req.json()
  return await AuthService.restore_password(session, req['current_user'], payload)
