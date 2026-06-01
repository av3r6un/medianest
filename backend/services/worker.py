from __future__ import annotations

import asyncio
from datetime import datetime as dt
from pathlib import Path
import shutil

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from backend.models import DownloadJob, JobEvent, JobState
from .ffmpeg import FFmpegService


class WorkerService:
  
  def __init__(self, session_maker: async_sessionmaker[AsyncSession]) -> None:
    self.session_maker = session_maker
    self.tasks: set[asyncio.Task] = set()
    self.processes = {}
    self.paused = False
    self.stopped = asyncio.Event()

  async def run(self) -> None:
    from backend import settings

    await self._recover_interrupted_jobs()
    await self._cleanup_finished_temp_files()
    while not self.stopped.is_set():
      if not self.paused:
        await self._fill_slots()
      try:
        await asyncio.wait_for(self.stopped.wait(), timeout=settings.WORKER_POLL_INTERVAL)
      except TimeoutError:
        pass

  async def stop(self) -> None:
    self.stopped.set()
    await asyncio.gather(
      *(self._terminate_process(process) for process in self.processes.values()),
      return_exceptions=True,
    )
    for task in self.tasks:
      task.cancel()
    if self.tasks:
      await asyncio.gather(*self.tasks, return_exceptions=True)

  def pause(self) -> dict:
    self.paused = True
    return self.status

  def resume(self) -> dict:
    self.paused = False
    return self.status

  @property
  def status(self) -> dict:
    return dict(paused=self.paused, running_jobs=list(self.processes.keys()))

  async def cancel_job(self, job_uid: str) -> bool:
    process = self.processes.get(job_uid)
    if not process:
      return False
    if process.returncode is None:
      await self._terminate_process(process)
      return True
    return False

  async def _fill_slots(self) -> None:
    from backend import settings

    self.tasks = {task for task in self.tasks if not task.done()}
    while len(self.tasks) < settings.MAX_CONCURRENT_JOBS:
      job_uid = await self._claim_job()
      if not job_uid:
        break
      self.tasks.add(asyncio.create_task(self._run_job(job_uid)))

  async def _claim_job(self) -> str | None:
    async with self.session_maker() as session:
      result = await session.execute(select(DownloadJob).where(DownloadJob.state == JobState.queued.value).limit(1))
      job = result.scalars().first()
      if not job:
        return None
      job.transition(JobState.running, 'starting')
      job.started_at = dt.now()
      await self._event(session, job.uid, 'running', 'Job started')
      await session.commit()
      return job.uid

  async def _terminate_process(self, process) -> None:
    from backend import settings

    if process.returncode is not None:
      return
    process.terminate()
    try:
      await asyncio.wait_for(process.wait(), timeout=settings.PROCESS_TERMINATE_TIMEOUT)
    except TimeoutError:
      if process.returncode is None:
        process.kill()
        await process.wait()

  async def _recover_interrupted_jobs(self) -> None:
    async with self.session_maker() as session:
      result = await session.execute(
        select(DownloadJob).where(
          DownloadJob.state.in_((JobState.running.value, JobState.cancel_requested.value))
        )
      )
      jobs = result.scalars().all()
      for job in jobs:
        job.state = JobState.failed.value
        job.current_phase = 'failed'
        job.failure_reason = 'Worker restarted before job finished'
        await self._event(session, job.uid, 'failed', job.failure_reason)
      await session.commit()

  async def _cleanup_finished_temp_files(self) -> None:
    from backend import settings

    async with self.session_maker() as session:
      result = await session.execute(
        select(DownloadJob).where(
          DownloadJob.state.in_((JobState.failed.value, JobState.cancelled.value))
        )
      )
      jobs = result.scalars().all()
      for job in jobs:
        temp_path = settings.WORK_DIR / f'{job.uid}.mp4'
        temp_path.unlink(missing_ok=True)

  async def _run_job(self, job_uid: str) -> None:
    from backend import settings

    async with self.session_maker() as session:
      job = await DownloadJob.first(session, uid=job_uid)
      if not job:
        return
      temp_path = settings.WORK_DIR / f'{job.uid}.mp4'
      temp_path.parent.mkdir(parents=True, exist_ok=True)
      command = FFmpegService.command(job, temp_path)
      duration_seconds = await FFmpegService.probe_duration(job)
      await self._event(
        session,
        job.uid,
        'ffmpeg_command',
        'ffmpeg process started',
        dict(command=command, duration_seconds=duration_seconds),
      )
      await session.commit()

    process = await asyncio.create_subprocess_exec(
      *command,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
    )
    self.processes[job_uid] = process
    progress_task = asyncio.create_task(self._read_progress(job_uid, process.stdout, duration_seconds))
    stderr_task = asyncio.create_task(process.stderr.read())
    await process.wait()
    await progress_task
    stderr = await stderr_task
    self.processes.pop(job_uid, None)
    stderr_tail = stderr.decode(errors='replace').splitlines()[-20:] if stderr else []

    async with self.session_maker() as session:
      job = await DownloadJob.first(session, uid=job_uid)
      if not job:
        temp_path.unlink(missing_ok=True)
        return
      if job.state == JobState.cancel_requested.value:
        temp_path.unlink(missing_ok=True)
        job.transition(JobState.cancelled, 'cancelled')
        await self._event(session, job.uid, 'cancelled', 'Job cancelled')
      elif process.returncode == 0:
        target_path = Path(job.target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_path), str(target_path))
        job.progress_percent = 100
        job.completed_at = dt.now()
        job.transition(JobState.completed, 'completed')
        await self._event(session, job.uid, 'completed', 'Job completed', dict(target_path=str(target_path)))
      else:
        temp_path.unlink(missing_ok=True)
        job.state = JobState.failed.value
        job.current_phase = 'failed'
        job.failure_reason = '\n'.join(stderr_tail)
        await self._event(session, job.uid, 'failed', 'ffmpeg process failed', dict(returncode=process.returncode, logs=stderr_tail))
      await session.commit()

  async def _read_progress(self, job_uid: str, stream, duration_seconds: float | None = None) -> None:
    if not stream:
      return
    async for raw in stream:
      progress = FFmpegService.parse_progress(raw.decode(errors='replace'))
      if not progress:
        continue
      key, value = progress
      if key not in ('out_time', 'speed', 'progress'):
        continue
      async with self.session_maker() as session:
        job = await DownloadJob.first(session, uid=job_uid)
        if not job:
          return
        if key == 'out_time':
          job.processed_time = value
          job.current_phase = 'encoding'
          seconds = FFmpegService.seconds_from_progress_time(value)
          if duration_seconds and seconds is not None:
            job.progress_percent = min(99, max(job.progress_percent, int(seconds / duration_seconds * 100)))
          elif job.progress_percent == 0:
            job.progress_percent = 1
        if key == 'speed':
          job.speed = value
        if key == 'progress' and value == 'end':
          job.current_phase = 'finalizing'
          job.progress_percent = max(job.progress_percent, 99)
        await session.commit()

  @staticmethod
  async def _event(session: AsyncSession, job_uid: str, event_type: str, message: str, payload: dict | None = None) -> None:
    uid = await JobEvent.create_uid(session)
    session.add(JobEvent(uid, job_uid, event_type, message, payload))
