from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from backend.exceptions import JSRError
from backend.models import DownloadJob, JobEvent, JobState
from .ffmpeg import FFmpegService


class JobService:
  ACTIVE_STATES = (
    JobState.queued.value,
    JobState.running.value,
    JobState.cancel_requested.value,
    JobState.retrying.value,
  )
  
  @classmethod
  async def all(cls, session: AsyncSession, state: str | None = None) -> list[dict]:
    filters = dict(state=state) if state else {}
    jobs = await DownloadJob.all(session, **filters)
    return [job.json for job in jobs]

  @classmethod
  async def get(cls, session: AsyncSession, uid: str) -> dict:
    job = await cls.get_job(session, uid)
    return job.json

  @classmethod
  async def events(cls, session: AsyncSession, uid: str) -> list[dict]:
    job = await cls.get_job(session, uid)
    return [event.json for event in job.events]

  @staticmethod
  async def get_job(session: AsyncSession, uid: str) -> DownloadJob:
    job = await DownloadJob.first(session, uid=uid)
    if not job: raise JSRError('not_found', message=f'Job[{uid}] not found!')
    return job

  @classmethod
  async def create(cls, session: AsyncSession, payload: dict) -> dict:
    data = cls._prepare_job_data(payload)
    await cls._check_duplicate_target(session, data['target_path'], data.pop('allow_duplicate', False))
    uid = await DownloadJob.create_uid(session)
    job = DownloadJob(uid=uid, **data)
    session.add(job)
    event_uid = await JobEvent.create_uid(session)
    event = JobEvent(event_uid, job.uid, 'created', 'Job queued', dict(state=job.state))
    session.add(event)
    await session.flush()
    await session.refresh(job)
    return job.json

  @classmethod
  async def update(cls, session: AsyncSession, uid: str, payload: dict) -> dict:
    job = await cls.get_job(session, uid)
    if job.state not in (JobState.queued.value, JobState.failed.value, JobState.cancelled.value):
      raise JSRError('invalid_payload', message=f'Cannot update job in {job.state} state')
    data = cls._prepare_job_data(dict(job.json, **payload))
    await job.edit(session, **data)
    await cls._event(session, job.uid, 'updated', 'Job updated')
    return job.json

  @classmethod
  async def cancel(cls, session: AsyncSession, uid: str, worker=None) -> dict:
    job = await cls.get_job(session, uid)
    if job.state == JobState.queued.value:
      job.transition(JobState.cancelled, 'cancelled')
      await cls._event(session, job.uid, 'cancelled', 'Queued job cancelled')
    elif job.state == JobState.running.value:
      job.transition(JobState.cancel_requested, 'cancel_requested')
      if worker:
        await worker.cancel_job(job.uid)
      await cls._event(session, job.uid, 'cancel_requested', 'Job cancellation requested')
    else:
      raise JSRError('invalid_payload', message=f'Cannot cancel job in {job.state} state')
    await session.flush()
    return job.json

  @classmethod
  async def retry(cls, session: AsyncSession, uid: str, payload: dict | None = None) -> dict:
    job = await cls.get_job(session, uid)
    if job.state not in (JobState.failed.value, JobState.cancelled.value):
      raise JSRError('invalid_payload', message=f'Cannot retry job in {job.state} state')
    if payload:
      data = cls._prepare_job_data(dict(job.json, **payload))
      await job.edit(session, **data)
    job.transition(JobState.retrying, 'retrying')
    job.transition(JobState.queued, 'queued')
    job.progress_percent = 0
    job.processed_time = None
    job.speed = None
    job.failure_reason = None
    job.retry_count += 1
    await cls._event(session, job.uid, 'retrying', 'Job queued for retry', dict(retry_count=job.retry_count))
    await session.flush()
    return job.json

  @classmethod
  async def dry_run(cls, payload: dict) -> dict:
    data = cls._prepare_job_data(payload)
    return dict(
      target_filename=data['target_filename'],
      target_plex_folder=data['target_plex_folder'],
      target_path=data['target_path'],
      selected_streams=data['selected_streams'],
      encoder_options=data['encoder_options'],
      command_preview=cls._command_preview(data),
      would_create_job=False,
    )

  @classmethod
  def _prepare_job_data(cls, payload: dict) -> dict:
    from backend import settings
    source_url = cls._validate_url(payload.get('source_url'), 'source_url')
    subtitles_url = payload.get('subtitles_url')
    if subtitles_url:
      subtitles_url = cls._validate_url(subtitles_url, 'subtitles_url')
    cls._check_url_allowed(source_url)
    target_folder, target_filename, target_path = cls._build_target_path(
      settings.PLEX_MEDIA_ROOT,
      payload.get('title'),
      payload.get('season'),
      payload.get('episode'),
    )
    selected_streams = cls._merge_selected_streams(payload.get('selected_streams'))
    encoder_options = cls._merge_encoder_options(payload.get('encoder_options'))
    data = dict(payload)
    source_user_agent = payload.get('source_user_agent')
    if source_user_agent is not None:
      source_user_agent = str(source_user_agent).strip() or None
    data.update(
      source_url=source_url,
      subtitles_url=subtitles_url,
      source_user_agent=source_user_agent,
      selected_streams=selected_streams,
      encoder_options=encoder_options,
      target_filename=target_filename,
      target_plex_folder=target_folder,
      target_path=str(target_path),
    )
    return data

  @classmethod
  async def _check_duplicate_target(cls, session: AsyncSession, target_path: str, allow_duplicate: bool) -> None:
    if allow_duplicate:
      return
    for state in cls.ACTIVE_STATES:
      duplicate = await DownloadJob.first(session, target_path=target_path, state=state)
      if duplicate:
        raise JSRError('conflict', message=f'Active job already targets {target_path}')

  @staticmethod
  def _merge_selected_streams(selected_streams: dict | None) -> dict:
    from backend import settings

    defaults = dict(
      video=getattr(settings, 'DEFAULT_VIDEO_STREAM', '0:v:1'),
      audio=getattr(settings, 'DEFAULT_AUDIO_STREAM', '0:a:1'),
      subtitles=getattr(settings, 'DEFAULT_SUBTITLE_STREAM', '1:0'),
    )
    return {**defaults, **(selected_streams or {})}

  @staticmethod
  def _merge_encoder_options(encoder_options: dict | None) -> dict:
    from backend import settings

    defaults = dict(
      encoder=FFmpegService.resolve_encoder(settings.VIDEO_ENCODER),
      preset=settings.PRESET,
      quality=str(settings.QUALITY),
      audio_bitrate=settings.AUDIO_BITRATE,
    )
    merged = {**defaults, **(encoder_options or {})}
    merged['encoder'] = FFmpegService.resolve_encoder(merged.get('encoder'))
    return merged

  @staticmethod
  def _validate_url(value: str | None, field: str) -> str:
    if not value:
      raise JSRError('invalid_payload', message=f'{field} is required')
    value = str(value).strip()
    parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
      raise JSRError('invalid_payload', message=f'{field} must be an http or https URL')
    return value

  @staticmethod
  def _command_preview(data: dict) -> list[str]:
    job = SimpleNamespace(
      source_url=data['source_url'],
      subtitles_url=data.get('subtitles_url'),
      output_title=data['output_title'],
      selected_streams=data['selected_streams'],
      encoder_options=data['encoder_options'],
    )
    return FFmpegService.command(job, Path(data['target_path']), progress=False)

  @staticmethod
  def _safe_name(value: str, field: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', ' ', value).strip()
    value = re.sub(r'\s+', ' ', value)
    if not value or value in ('.', '..'):
      raise JSRError('invalid_payload', message=f'{field} is unsafe')
    return value.rstrip('. ')

  @classmethod
  def _build_target_path(cls, plex_root: Path, show_name: str, season: int, episode: int) -> tuple[str, str, Path]:
    safe_show = cls._safe_name(show_name, 'show_name')
    try:
      season = int(season)
      episode = int(episode)
    except (TypeError, ValueError):
      raise JSRError('invalid_payload', message='season and episode must be integers')
    if season < 1 or episode < 1:
      raise JSRError('invalid_payload', message='season and episode must be positive')
    season_folder = f'Season {season:02d}'
    filename = f'{safe_show} - S{season:02d}E{episode:02d}.mp4'
    relative_folder = Path(safe_show) / season_folder
    target_path = plex_root / relative_folder / filename
    plex_root_resolved = plex_root.resolve()
    target_resolved = target_path.resolve()
    try:
      target_resolved.relative_to(plex_root_resolved)
    except ValueError:
      raise JSRError('invalid_payload', message='Target path is outside PLEX_MEDIA_ROOT')
    return relative_folder.as_posix(), filename, target_resolved

  @staticmethod
  def _check_url_allowed(url: str) -> None:
    from backend import settings

    host = urlparse(url).hostname or ''
    if settings.URL_ALLOWLIST and host not in settings.URL_ALLOWLIST:
      raise JSRError('forbidden', message=f'Host is not allowed: {host}')
    if settings.URL_BLOCKLIST and host in settings.URL_BLOCKLIST:
      raise JSRError('forbidden', message=f'Host is blocked: {host}')

  @staticmethod
  async def _event(session: AsyncSession, job_uid: str, event_type: str, message: str, payload: dict | None = None) -> None:
    uid = await JobEvent.create_uid(session)
    session.add(JobEvent(uid, job_uid, event_type, message, payload))
