from pathlib import Path
import os

from yaml import safe_load

from backend.exceptions import JSRError


class Settings:
  def __init__(self) -> None:
    self._load_yaml()

  def _load_yaml(self) -> None:
    config_path = Path(__file__).with_name('settings.yaml')
    if not config_path.exists():
      raise JSRError('not_found', message='Config file not found!')
    with config_path.open('r', encoding='utf-8') as f:
      data = safe_load(f) or {}
      self.__dict__.update(data)
    self.WORK_DIR = Path(self.WORK_DIR)
    self.PLEX_MEDIA_ROOT = Path(self.PLEX_MEDIA_ROOT)
    return data

  @property
  def api_info(self) -> dict:
    return dict(
      name='alloha-downloader',
      status='ok',
      version='0.1.0',
    )

  @property
  def diagnostics(self) -> dict:
    app = dict(host=self.APP_HOST, port=self.APP_PORT)
    storage = dict(
      database_configured=bool(os.getenv('DB_URL')),
      work_dir=str(self.WORK_DIR),
      plex_media_root=str(self.PLEX_MEDIA_ROOT),
    )
    downloads = dict(
      default_request_headers=[
        header.split(':', 1)[0] for header in getattr(self, 'DEFAULT_REQUEST_HEADERS', [])
      ],
      default_video_stream=getattr(self, 'DEFAULT_VIDEO_STREAM', '0:v:1'),
      default_audio_stream=getattr(self, 'DEFAULT_AUDIO_STREAM', '0:a:1'),
      default_subtitle_stream=getattr(self, 'DEFAULT_SUBTITLE_STREAM', '1:0'),
    )
    encoder = dict(encoder=self.VIDEO_ENCODER, preset=self.PRESET, quality=self.QUALITY, audio_bitrate=self.AUDIO_BITRATE)
    auth = dict(bearer_token_configured=bool(os.getenv('SECRET_KEY')))
    plex = dict(
      server_url_configured=bool(getattr(self, 'PLEX_SERVER_URL', '')),
      token_configured=bool(getattr(self, 'PLEX_TOKEN', '')),
    )
    return dict(
      app=app,
      storage=storage,
      downloads=downloads,
      encoder=encoder,
      queue=dict(max_concurrent_jobs=self.MAX_CONCURRENT_JOBS),
      auth=auth,
      plex=plex,
    )
