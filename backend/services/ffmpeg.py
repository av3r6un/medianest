from __future__ import annotations

import asyncio
from pathlib import Path
from functools import lru_cache
import subprocess


class FFmpegService:
  
  @staticmethod
  def command(job, output_path: Path, *, progress: bool = True) -> list[str]:
    from backend import settings

    streams = job.selected_streams
    encoder = job.encoder_options
    command = [
      settings.FFMPEG_BINARY,
      '-hide_banner',
      '-y',
      *FFmpegService.input_options(job),
      '-i',
      job.source_url,
    ]
    if job.subtitles_url:
      command.extend([*FFmpegService.input_options(job), '-i', job.subtitles_url])
    video_encoder = FFmpegService.resolve_encoder(encoder['encoder'])
    command.extend([
      '-map', streams['video'],
      '-map', streams['audio'],
    ])
    if job.subtitles_url:
      command.extend(['-map', streams['subtitles']])
    command.extend([
      '-c:v', video_encoder,
      '-preset', encoder['preset'],
      '-crf', str(encoder['quality']),
      '-c:a', 'aac',
      '-b:a', encoder['audio_bitrate'],
      '-metadata:s:a:0', 'language=eng',
    ])
    if job.subtitles_url:
      command.extend([
        '-c:s', 'mov_text',
        '-metadata:s:s:0', 'language=eng',
        '-disposition:s:0', 'default',
      ])
    command.extend([
      '-movflags', '+faststart',
      '-metadata', f'title={job.output_title}',
    ])
    if progress:
      command.extend(['-progress', 'pipe:1', '-nostats'])
    command.append(str(output_path))
    return command

  @staticmethod
  def input_options(job=None) -> list[str]:
    return [
      '-protocol_whitelist',
      'file,http,https,tcp,tls',
      '-headers',
      FFmpegService.headers(job),
      '-rw_timeout',
      '15000000',
      '-reconnect',
      '1',
      '-reconnect_streamed',
      '1',
      '-reconnect_delay_max',
      '5',
    ]

  @staticmethod
  def headers(job=None) -> str:
    from backend import settings

    headers = list(getattr(settings, 'DEFAULT_REQUEST_HEADERS', []))
    job_user_agent = None
    if job:
      job_user_agent = getattr(job, 'source_user_agent', None)
      if job_user_agent:
        headers = [header for header in headers if not header.lower().startswith('user-agent:')]
        headers.append(f'User-Agent: {job_user_agent}')
    return ''.join(f'{header}\r\n' for header in headers)

  @staticmethod
  def resolve_encoder(encoder: str | None) -> str:
    requested = str(encoder or '').strip() or 'libx265'
    if requested != 'hevc_nvenc':
      return requested
    if FFmpegService._encoder_available('hevc_nvenc'):
      return requested
    return 'libx265'

  @staticmethod
  @lru_cache(maxsize=16)
  def _encoder_available(encoder: str) -> bool:
    from backend import settings

    ffmpeg_binary = getattr(settings, 'FFMPEG_BINARY', 'ffmpeg')
    try:
      result = subprocess.run(
        [ffmpeg_binary, '-hide_banner', '-encoders'],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
      )
    except (OSError, subprocess.SubprocessError):
      return False
    if result.returncode != 0:
      return False
    return encoder in result.stdout

  @staticmethod
  def parse_progress(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if '=' not in line:
      return None
    return tuple(line.split('=', 1))

  @staticmethod
  async def probe_duration(job) -> float | None:
    from backend import settings

    process = await asyncio.create_subprocess_exec(
      getattr(settings, 'FFPROBE_BINARY', 'ffprobe'),
      '-v', 'error',
      *FFmpegService.input_options(job),
      '-show_entries', 'format=duration',
      '-of', 'default=noprint_wrappers=1:nokey=1',
      job.source_url,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
    )
    try:
      stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)
    except TimeoutError:
      process.kill()
      await process.communicate()
      return None
    if process.returncode != 0:
      return None
    try:
      duration = float(stdout.decode().strip())
    except ValueError:
      return None
    return duration if duration > 0 else None

  @staticmethod
  def seconds_from_progress_time(value: str) -> float | None:
    if not value:
      return None
    parts = value.split(':')
    if len(parts) != 3:
      return None
    try:
      hours = int(parts[0])
      minutes = int(parts[1])
      seconds = float(parts[2])
    except ValueError:
      return None
    return hours * 3600 + minutes * 60 + seconds
