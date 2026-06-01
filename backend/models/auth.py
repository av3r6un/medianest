from __future__ import annotations

from datetime import datetime as dt

import bcrypt
from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.exceptions import JSRError
from .base import Base


class User(Base):
  __tablename__ = 'users'

  uid: Mapped[str] = mapped_column(String(16), primary_key=True)
  login: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
  password_hash: Mapped[str] = mapped_column(Text, nullable=False)

  def __init__(self, uid: str, **kwargs) -> None:
    self.uid = uid
    self.login = self._validate_login(kwargs.get('login'))
    self.password_hash = self._validate_password(kwargs.get('password'))

  @staticmethod
  def _validate_login(value: str | None) -> str:
    value = str(value or '').strip().lower()
    if not value:
      raise JSRError('invalid_payload', message='login is required')
    if len(value) < 3:
      raise JSRError('invalid_payload', message='login must be at least 3 chars')
    return value

  @staticmethod
  def _validate_password(value: str | None) -> str:
    value = str(value or '')
    if len(value) < 8:
      raise JSRError('invalid_payload', message='password must be at least 8 chars')
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()

  @property
  def json(self) -> dict:
    return dict(uid=self.uid, login=self.login, created_at=self.created_ts, updated_at=self.updated_ts)


class RevokedToken(Base):
  __tablename__ = 'revoked_tokens'

  uid: Mapped[str] = mapped_column(String(16), primary_key=True)
  jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
  token_type: Mapped[str] = mapped_column(String(16), nullable=False)
  user_uid: Mapped[str] = mapped_column(String(16), nullable=False)
  expires_at: Mapped[dt | None] = mapped_column(DateTime, nullable=True)

  def __init__(self, uid: str, **kwargs) -> None:
    self.uid = uid
    self.jti = str(kwargs.get('jti') or '').strip()
    self.token_type = str(kwargs.get('token_type') or '').strip()
    self.user_uid = str(kwargs.get('user_uid') or '').strip()
    self.expires_at = kwargs.get('expires_at')
    if not self.jti:
      raise JSRError('invalid_payload', message='jti is required')
    if not self.token_type:
      raise JSRError('invalid_payload', message='token_type is required')
    if not self.user_uid:
      raise JSRError('invalid_payload', message='user_uid is required')
