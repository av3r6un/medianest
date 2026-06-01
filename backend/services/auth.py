from __future__ import annotations

from datetime import datetime as dt

from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.exceptions import JSRError
from backend.models import RevokedToken, User
from backend.utils.jwt import create_token, decode_token
from backend.utils.security import check_pw, hash_password


class AuthService:

  @classmethod
  async def login(cls, session: AsyncSession, payload: dict) -> dict:
    login = cls._require_string(payload, 'login').lower()
    password = cls._require_string(payload, 'password')
    user = await User.first(session, login=login)
    if not user or not check_pw(password, user.password_hash):
      raise JSRError('unauthorized', message='Invalid login or password')
    access_token, _, access_expires_at = create_token(user.uid, fresh=True)
    refresh_token, _, refresh_expires_at = create_token(user.uid, fresh=False)
    return dict(
      access_token=access_token,
      refresh_token=refresh_token,
      token_type='bearer',
      access_expires_at=int(access_expires_at.timestamp()),
      refresh_expires_at=int(refresh_expires_at.timestamp()),
      user=user.json,
    )

  @classmethod
  async def refresh(cls, session: AsyncSession, payload: dict) -> dict:
    token = cls._require_string(payload, 'refresh_token')
    try:
      payload = decode_token(token)
    except ExpiredSignatureError:
      raise JSRError('token_expired')
    except InvalidTokenError:
      raise JSRError('invalid_token')
    if payload.get('type') != 'refresh':
      raise JSRError('invalid_token')
    revoked = await RevokedToken.first(session, jti=payload.get('jti'))
    if revoked:
      raise JSRError('invalid_token')
    user = await User.first(session, uid=payload.get('sub'))
    if not user:
      raise JSRError('invalid_token')
    await cls._revoke_token(session, payload, 'refresh')
    access_token, _, access_expires_at = create_token(user.uid, fresh=True)
    refresh_token, _, refresh_expires_at = create_token(user.uid, fresh=False)
    return dict(
      access_token=access_token,
      refresh_token=refresh_token,
      token_type='bearer',
      access_expires_at=int(access_expires_at.timestamp()),
      refresh_expires_at=int(refresh_expires_at.timestamp()),
    )

  @classmethod
  async def logout(cls, session: AsyncSession, current_user: dict, payload: dict) -> dict:
    await cls._revoke_token(session, current_user.get('token', {}), 'access')
    refresh_token = (payload or {}).get('refresh_token')
    if refresh_token:
      try:
        refresh_payload = decode_token(str(refresh_token))
      except (ExpiredSignatureError, InvalidTokenError):
        refresh_payload = None
      if refresh_payload and refresh_payload.get('sub') == current_user.get('uid'):
        await cls._revoke_token(session, refresh_payload, 'refresh')
    return dict(logged_out=True)

  @classmethod
  async def restore_password(cls, session: AsyncSession, current_user: dict, payload: dict) -> tuple[dict, str]:
    old_password = cls._require_string(payload, 'old_password')
    new_password = cls._require_string(payload, 'new_password')
    if old_password == new_password:
      raise JSRError('invalid_payload', message='new_password must differ from old_password')
    user = await User.first(session, uid=current_user.get('uid'))
    if not user:
      raise JSRError('not_found', message=f'User[{current_user.get("uid")}] not found!')
    if not check_pw(old_password, user.password_hash):
      raise JSRError('unauthorized', message='Invalid old_password')
    user.password_hash = hash_password(new_password)
    return dict(restored=True), 'Password restored'

  @staticmethod
  def _require_string(payload: dict, field: str) -> str:
    value = str((payload or {}).get(field, '')).strip()
    if not value:
      raise JSRError('invalid_payload', message=f'{field} is required')
    return value

  @staticmethod
  async def _revoke_token(session: AsyncSession, payload: dict, token_type: str) -> None:
    jti = str(payload.get('jti') or '').strip()
    user_uid = str(payload.get('sub') or '').strip()
    if not jti or not user_uid:
      return
    exists = await RevokedToken.first(session, jti=jti)
    if exists:
      return
    uid = await RevokedToken.create_uid(session)
    exp = payload.get('exp')
    expires_at = dt.fromtimestamp(exp) if isinstance(exp, (int, float)) else None
    session.add(RevokedToken(uid=uid, jti=jti, token_type=token_type, user_uid=user_uid, expires_at=expires_at))
