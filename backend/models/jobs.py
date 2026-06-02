from __future__ import annotations

from datetime import datetime as dt
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.exceptions import JSRError
from .base import Base


class JobState(str, Enum):
  queued = 'queued'
  running = 'running'
  completed = 'completed'
  failed = 'failed'
  cancel_requested = 'cancel_requested'
  cancelled = 'cancelled'
  retrying = 'retrying'


class DownloadJob(Base):
  __tablename__ = 'download_jobs'

  uid: Mapped[str] = mapped_column(String(16), primary_key=True)
  source_url: Mapped[str] = mapped_column(Text, nullable=False)
  subtitles_url: Mapped[str | None] = mapped_column(Text, nullable=True)
  output_title: Mapped[str] = mapped_column(String(255), nullable=False)
  title: Mapped[str] = mapped_column(String(255), nullable=False)
  season: Mapped[int] = mapped_column(Integer, nullable=False)
  episode: Mapped[int] = mapped_column(Integer, nullable=False)
  target_filename: Mapped[str] = mapped_column(String(255), nullable=False)
  target_plex_folder: Mapped[str] = mapped_column(Text, nullable=False)
  target_path: Mapped[str] = mapped_column(Text, nullable=False)
  selected_streams: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
  encoder_options: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
  proxy_override: Mapped[str | None] = mapped_column(Text, nullable=True)
  source_user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
  state: Mapped[str] = mapped_column(String(32), default=JobState.queued.value, nullable=False)
  progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
  processed_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
  speed: Mapped[str | None] = mapped_column(String(32), nullable=True)
  current_phase: Mapped[str] = mapped_column(String(64), default='queued', nullable=False)
  failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
  retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
  started_at: Mapped[dt | None] = mapped_column(DateTime, nullable=True)
  completed_at: Mapped[dt | None] = mapped_column(DateTime, nullable=True)

  events: Mapped[list['JobEvent']] = relationship(
    back_populates='job',
    cascade='all, delete-orphan',
    order_by='JobEvent.created_at',
  )

  def __init__(self, uid: str, **kwargs) -> None:
    self.uid = uid
    self.source_url = self._validate_required('source_url', **kwargs)
    self.subtitles_url = kwargs.get('subtitles_url')
    self.output_title = self._validate_required('output_title', **kwargs)
    self.title = self._validate_required('title', **kwargs)
    self.season = self._validate_positive_int('season', **kwargs)
    self.episode = self._validate_positive_int('episode', **kwargs)
    self.target_filename = self._validate_required('target_filename', **kwargs)
    self.target_plex_folder = self._validate_required('target_plex_folder', **kwargs)
    self.target_path = self._validate_required('target_path', **kwargs)
    self.selected_streams = kwargs.get('selected_streams') or {}
    self.encoder_options = kwargs.get('encoder_options') or {}
    self.proxy_override = kwargs.get('proxy_override')
    self.source_user_agent = kwargs.get('source_user_agent')
    self.state = JobState.queued.value
    self.current_phase = 'queued'

  def _validate_required(self, field: str, **kwargs) -> str:
    value = str(kwargs.get(field, '')).strip()
    if not value:
      raise JSRError('invalid_payload', message=f'{field} is required')
    return value

  def _validate_positive_int(self, field: str, **kwargs) -> int:
    try:
      value = int(kwargs.get(field))
    except (TypeError, ValueError):
      raise JSRError('invalid_payload', message=f'{field} must be an integer')
    if value < 1:
      raise JSRError('invalid_payload', message=f'{field} must be positive')
    return value

  def transition(self, state: JobState, phase: str | None = None) -> None:
    allowed = {
      JobState.queued.value: {JobState.running.value, JobState.cancel_requested.value, JobState.cancelled.value},
      JobState.running.value: {JobState.completed.value, JobState.failed.value, JobState.cancel_requested.value},
      JobState.cancel_requested.value: {JobState.cancelled.value, JobState.failed.value},
      JobState.cancelled.value: {JobState.retrying.value},
      JobState.failed.value: {JobState.retrying.value},
      JobState.retrying.value: {JobState.queued.value},
      JobState.completed.value: set(),
    }
    if state.value not in allowed.get(self.state, set()):
      raise JSRError('invalid_payload', message=f'Cannot transition job from {self.state} to {state.value}')
    self.state = state.value
    if phase:
      self.current_phase = phase

  @property
  def json(self) -> dict:
    return dict(
      uid=self.uid,
      source_url=self.source_url,
      subtitles_url=self.subtitles_url,
      output_title=self.output_title,
      title=self.title,
      season=self.season,
      episode=self.episode,
      target_filename=self.target_filename,
      target_plex_folder=self.target_plex_folder,
      target_path=self.target_path,
      selected_streams=self.selected_streams,
      encoder_options=self.encoder_options,
      source_user_agent=self.source_user_agent,
      state=self.state,
      progress_percent=self.progress_percent,
      processed_time=self.processed_time,
      speed=self.speed,
      current_phase=self.current_phase,
      failure_reason=self.failure_reason,
      retry_count=self.retry_count,
      started_at=int(self.started_at.timestamp()) if self.started_at else None,
      completed_at=int(self.completed_at.timestamp()) if self.completed_at else None
    )


class JobEvent(Base):
  __tablename__ = 'job_events'

  uid: Mapped[str] = mapped_column(String(16), primary_key=True)
  job_uid: Mapped[str] = mapped_column(ForeignKey('download_jobs.uid'), nullable=False)
  event_type: Mapped[str] = mapped_column(String(64), nullable=False)
  message: Mapped[str] = mapped_column(Text, nullable=False)
  payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

  job: Mapped[DownloadJob] = relationship(
    back_populates='events',
  )

  def __init__(self, uid: str, job_uid: str, event_type: str, message: str, payload: dict | None = None) -> None:
    self.uid = uid
    self.job_uid = job_uid
    self.event_type = event_type
    self.message = message
    self.payload = payload or {}

  @property
  def json(self) -> dict:
    return dict(
      uid=self.uid,
      job_uid=self.job_uid,
      event_type=self.event_type,
      message=self.message,
      payload=self.payload,
      created_at=self.created_ts,
    )
