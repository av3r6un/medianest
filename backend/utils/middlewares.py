from aiohttp.web import json_response, middleware, StreamResponse, HTTPException, Request
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from aiohttp.web_exceptions import HTTPNotFound
from jwt import ExpiredSignatureError, InvalidTokenError
from backend.app_keys import DB_SESSIONMAKER
from backend.exceptions import JSRError
from .jwt import decode_token
import inspect

@middleware
async def db_middleware(req: Request, handler, *args, **kwargs):
  session_factory: async_sessionmaker[AsyncSession] = req.app[DB_SESSIONMAKER]
  async with session_factory() as session:
    try:
      req['session'] = session
      response = await handler(req, *args, **kwargs)
      if getattr(response, 'status', 200) >= 400:
        await session.rollback()
      else:
        await session.commit()
      return response
    except HTTPNotFound:
      await session.rollback()
      return json_response(dict(status='error', message='Requested page is not found'), status=404)
    except Exception as e:
      await session.rollback()
      raise e
      # print(e)
      # return json_response(dict(status='error', message=str(e)))
  

@middleware
async def response_middleware(req: Request, handler, *args, **kwargs):
  try:
    call_kwargs = {}
    try:
      sig = inspect.signature(handler)
      params = sig.parameters
      if 'session' in params or any(p.kind == p.VAR_KEYWORD for p in params.values()):
        call_kwargs['session'] = req.get('session')
    except (TypeError, ValueError):
      pass
    
    result = await handler(req, *args, **call_kwargs, **kwargs)
    if isinstance(result, StreamResponse):
      return result
    if isinstance(result, tuple):
      body, message = result
      return json_response(dict(status='success', body=body, message=message))
    return json_response(dict(status='success', body=result))
  except JSRError as e:
    return json_response(**e.json)
  except HTTPException:
    raise
  except Exception as e:
    return json_response(dict(status='error', message=str(e)), status=500)
      

@middleware
async def jwt_middleware(req: Request, handler, *args, **kwargs):
  from backend import settings
  
  route_error = getattr(req.match_info, 'http_exception', None)
  
  if isinstance(route_error, HTTPNotFound):
    raise route_error
  
  if req.path in set(settings.NOT_SECURED_PATHS):
    return await handler(req, session=req.get('session'))
  
  auth_header = req.headers.get('Authorization')
  if not auth_header or not auth_header.startswith('Bearer '):
    raise JSRError('missing_auth_header')
  
  token = auth_header.split(' ')[1]
  try:
    from backend.models import RevokedToken

    payload = decode_token(token)
    if payload.get('type') != 'access': raise JSRError('invalid_token')
    revoked = await RevokedToken.first(req.get('session'), jti=payload.get('jti'))
    if revoked: raise JSRError('invalid_token')
    req['current_user'] = dict(uid=payload['sub'], token=payload)
  except ExpiredSignatureError: raise JSRError('token_expired')
  except (InvalidTokenError, KeyError): raise JSRError('invalid_token')
  
  return await handler(req, session=req.get('session'))
  

middlewares = [db_middleware, response_middleware, jwt_middleware]
