from datetime import datetime as dt, timedelta as delta
from uuid import uuid4
from pytz import timezone
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
import os

alg = 'HS256'

def _create_token(user_uid: str, fresh: bool = True):
  jti = uuid4().hex
  expires_delta = delta(seconds=int(os.getenv('JWT_TOKEN_EXPIRES', 3600)) if fresh else int(os.getenv('JWT_REFRESH_TOKEN_EXPIRES', 2592000))) 
  expires_at = dt.now() + expires_delta
  payload = dict(
    sub=user_uid,
    type="access" if fresh else "refresh",
    jti=jti,
    iat=dt.now(tz=timezone('UTC')),
    exp=expires_at,
  )
  if not os.getenv('SECRET_KEY', None): raise RuntimeError('SECRET_KEY not found!')
  token = jwt.encode(payload, os.getenv('SECRET_KEY'), algorithm=alg)

  return token, jti, expires_at

def decode_token(token: str):
  return jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=[alg])

def create_token(user_uid: str, fresh: bool = True):
  return _create_token(user_uid, fresh)
