# Alloha Downloader

Small Python helper for turning a DASH video source and a WebVTT subtitles URL into a single MP4 file with `ffmpeg`.

The script is intentionally thin: it builds an `ffmpeg` command with browser-like request headers, optional proxy support, selected video/audio/subtitle streams, HEVC video encoding, AAC audio, and MP4-compatible subtitles.

Use it only for media that you are allowed to access and download.

## Requirements

- Python 3.14 or newer
- [`uv`](https://docs.astral.sh/uv/) for project setup
- `ffmpeg` and `ffprobe` available on `PATH`
- NVIDIA GPU with NVENC support, because the default video encoder is `hevc_nvenc`
- Optional local HTTP proxy, defaulting to `http://127.0.0.1:10809`

Check `ffmpeg`:

```cmd
ffmpeg -version
```

Check `ffprobe`:

```cmd
ffprobe -version
```

Check that NVENC is available:

```cmd
ffmpeg -hide_banner -encoders | findstr hevc_nvenc
```

## Setup

```cmd
uv sync
```

The CLI invokes the `ffmpeg` executable directly through `subprocess`. Backend dependencies are installed through the same project environment.

## Backend Runtime

The backend is an `aiohttp` application. Start it with:

```cmd
uv run python -m backend
```

Runtime settings come from `backend/config/settings.yaml`. The database URL is still read from `DB_URL` for Alembic and SQLAlchemy.
For production, prefer MySQL or MariaDB DSNs instead of SQLite.

```text
APP_HOST             HTTP bind host.
APP_PORT             HTTP bind port.
REQUEST_MAX_BYTES    Maximum accepted request body size.
WORK_DIR             Temporary worker directory.
PLEX_MEDIA_ROOT      Final Plex media root.
AUDIO_BITRATE        Default audio bitrate.
QUALITY              Default video quality.
PRESET               Default encoder preset.
VIDEO_ENCODER        Default video encoder.
DEFAULT_VIDEO_STREAM Default ffmpeg video stream selector.
DEFAULT_AUDIO_STREAM Default ffmpeg audio stream selector.
DEFAULT_SUBTITLE_STREAM Default ffmpeg subtitle stream selector.
DEFAULT_REQUEST_HEADERS Browser-like request headers passed to ffmpeg and ffprobe.
MAX_CONCURRENT_JOBS  Maximum concurrent background jobs.
WORKER_ENABLED       Whether the backend starts the worker loop.
WORKER_POLL_INTERVAL Queue polling interval in seconds.
PROCESS_TERMINATE_TIMEOUT Seconds to wait after terminate before killing a worker process.
FFMPEG_BINARY        ffmpeg executable name or absolute path.
FFPROBE_BINARY       ffprobe executable name or absolute path.
URL_ALLOWLIST        Optional list of allowed source URL hosts.
URL_BLOCKLIST        Optional list of blocked source URL hosts.
```

Server dependencies for the planned download worker:

- writable temporary working directory
- writable final Plex media root
- `ffmpeg` available on `PATH`
- optional GPU encoder support when configured
- writable Plex media root; Plex scans files from the filesystem

### API Response Contract

Successful backend responses use this envelope:

```json
{
  "status": "success",
  "body": {}
}
```

Errors use this envelope:

```json
{
  "status": "error",
  "message": "Human readable error"
}
```

Protected endpoints require:

```text
Authorization: Bearer <access_token>
```

`GET /health` is public and does not require authentication. `GET /config/diagnostics` is protected.

Common auth errors:

```yaml
missing_header:
  status: 401
  body:
    status: error
    message: Missing Authentication Header
invalid_token:
  status: 401
  body:
    status: error
    message: Invalid token
```

Protected routes accept JWT access tokens signed with `SECRET_KEY`.

### API: GET /health

```yaml
path: /health
method: GET
authentication: not required
headers: {}
query_parameters: {}
request_body: null
response_body:
  status: success
  body:
    name: alloha-downloader
    status: ok
    version: 0.1.0
status_codes:
  200: Service is running.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl http://127.0.0.1:8090/health
```

Example response:

```json
{
  "status": "success",
  "body": {
    "name": "alloha-downloader",
    "status": "ok",
    "version": "0.1.0"
  }
}
```

### API: GET /config/diagnostics

```yaml
path: /config/diagnostics
method: GET
authentication: required
headers:
  Authorization: Bearer <access_token>
query_parameters: {}
request_body: null
response_body:
  status: success
  body:
    app:
      host: 0.0.0.0
      port: 8090
    storage:
      database_configured: true
      work_dir: var/work
      plex_media_root: var/plex
    downloads:
      default_request_headers:
        - Accept
        - Accept-Language
        - Origin
        - Referer
        - User-Agent
      default_video_stream: 0:v:1
      default_audio_stream: 0:a:1
      default_subtitle_stream: 1:0
    encoder:
      encoder: hevc_nvenc
      preset: slow
      quality: "20"
      audio_bitrate: 160k
    queue:
      max_concurrent_jobs: 1
    auth:
      bearer_token_configured: true
    plex:
      server_url_configured: false
      token_configured: false
status_codes:
  200: Diagnostics returned.
  401: Missing or invalid bearer token.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
omitted_secret_fields:
  - SECRET_KEY
  - DB_URL value
  - DEFAULT_REQUEST_HEADERS values
```

Example request:

```cmd
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8090/config/diagnostics
```

Example response:

```json
{
  "status": "success",
  "body": {
    "app": {
      "host": "0.0.0.0",
      "port": 8090
    },
    "storage": {
      "database_configured": true,
      "work_dir": "var/work",
      "plex_media_root": "var/plex"
    },
    "downloads": {
      "default_request_headers": [
        "Accept",
        "Accept-Language",
        "Origin",
        "Referer",
        "User-Agent"
      ],
      "default_video_stream": "0:v:1",
      "default_audio_stream": "0:a:1",
      "default_subtitle_stream": "1:0"
    },
    "encoder": {
      "encoder": "hevc_nvenc",
      "preset": "slow",
      "quality": "18",
      "audio_bitrate": "160k"
    },
    "queue": {
      "max_concurrent_jobs": 1
    },
    "auth": {
      "bearer_token_configured": true
    },
    "plex": {
      "server_url_configured": false,
      "token_configured": false
    }
  }
}
```

### Job States

```text
queued
running
completed
failed
cancel_requested
cancelled
retrying
```

Stage 4 starts the worker when `WORKER_ENABLED: true`. The worker claims queued jobs, runs `ffmpeg`, writes progress fields, appends job events, and moves completed files into `PLEX_MEDIA_ROOT`.

### API: POST /jobs

```yaml
path: /jobs
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
  Content-Type: application/json
  User-Agent: optional, captured and stored per job for ffmpeg/ffprobe requests
request_body:
  source_url: string, required, http or https DASH/source URL
  subtitles_url: string, required, http or https subtitles URL
  output_title: string, required
  title: string, required
  season: integer, required, positive
  episode: integer, required, positive
  allow_duplicate: boolean, optional, defaults to false
  selected_streams:
    video: string, optional
    audio: string, optional
    subtitles: string, optional
  encoder_options:
    encoder: string, optional
    preset: string, optional
    quality: string, optional
    audio_bitrate: string, optional
response_body:
  status: success
  body:
    uid: string
    source_url: string
    subtitles_url: string|null
    source_user_agent: string|null
    output_title: string
    title: string
    season: integer
    episode: integer
    target_filename: string
    target_plex_folder: string
    target_path: string
    selected_streams: object
    encoder_options: object
    state: queued
    progress_percent: integer
    processed_time: string|null
    speed: string|null
    current_phase: string
    failure_reason: string|null
    retry_count: integer
    started_at: integer|null
    completed_at: integer|null
    created_at: integer
    updated_at: integer
status_codes:
  200: Job created and queued.
  400: Invalid payload, URL, stream options, or unsafe metadata.
  401: Missing or invalid bearer token.
  409: Active job already targets the same Plex output path.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl -X POST http://127.0.0.1:8090/jobs ^
  -H "Authorization: Bearer <access_token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"source_url\":\"https://example.com/manifest.mpd\",\"subtitles_url\":\"https://example.com/subtitles.vtt\",\"output_title\":\"Example Show S01E02\",\"title\":\"Example Show\",\"season\":1,\"episode\":2}"
```

Example response:

```json
{
  "status": "success",
  "body": {
    "uid": "Ab8XsAhPkzky5Gys",
    "source_url": "https://example.com/manifest.mpd",
    "subtitles_url": "https://example.com/subtitles.vtt",
    "source_user_agent": "MyClient/1.0",
    "output_title": "Example Show S01E02",
    "title": "Example Show",
    "season": 1,
    "episode": 2,
    "target_filename": "Example Show - S01E02.mp4",
    "target_plex_folder": "Example Show/Season 01",
    "target_path": "/plex/Example Show/Season 01/Example Show - S01E02.mp4",
    "selected_streams": {
      "video": "0:v:1",
      "audio": "0:a:1",
      "subtitles": "1:0"
    },
    "encoder_options": {
      "encoder": "hevc_nvenc",
      "preset": "slow",
      "quality": "18",
      "audio_bitrate": "160k"
    },
    "state": "queued",
    "progress_percent": 0,
    "processed_time": null,
    "speed": null,
    "current_phase": "queued",
    "failure_reason": null,
    "retry_count": 0,
    "started_at": null,
    "completed_at": null,
    "created_at": 1779169008,
    "updated_at": 1779169008
  }
}
```

Invalid request example:

```json
{
  "status": "error",
  "message": "source_url must be an http or https URL"
}
```

Duplicate target example:

```json
{
  "status": "error",
  "message": "Active job already targets /plex/Example Show/Season 01/Example Show - S01E02.mp4"
}
```

Pass `"allow_duplicate": true` only when intentionally creating another active job for the same target output path.

### API: POST /jobs:dry-run

```yaml
path: /jobs:dry-run
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
  Content-Type: application/json
request_body:
  source_url: string, required, http or https DASH/source URL
  subtitles_url: string, required, http or https subtitles URL
  output_title: string, required
  title: string, required
  season: integer, required, positive
  episode: integer, required, positive
  selected_streams: object, optional
  encoder_options: object, optional
response_body:
  status: success
  body:
    target_filename: string
    target_plex_folder: string
    target_path: string
    selected_streams: object
    encoder_options: object
    command_preview: array of strings
    would_create_job: false
status_codes:
  200: Dry-run preview returned and no job was created.
  400: Invalid payload, URL, stream options, or unsafe metadata.
  401: Missing or invalid bearer token.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl -X POST http://127.0.0.1:8090/jobs:dry-run ^
  -H "Authorization: Bearer <access_token>" ^
  -H "Content-Type: application/json" ^
  -d "{\"source_url\":\"https://example.com/manifest.mpd\",\"subtitles_url\":\"https://example.com/subtitles.vtt\",\"output_title\":\"Example Show S01E02\",\"title\":\"Example Show\",\"season\":1,\"episode\":2}"
```

Example response:

```json
{
  "status": "success",
  "body": {
    "target_filename": "Example Show - S01E02.mp4",
    "target_plex_folder": "Example Show/Season 01",
    "target_path": "/plex/Example Show/Season 01/Example Show - S01E02.mp4",
    "selected_streams": {
      "video": "0:v:1",
      "audio": "0:a:1",
      "subtitles": "1:0"
    },
    "encoder_options": {
      "encoder": "hevc_nvenc",
      "preset": "slow",
      "quality": "18",
      "audio_bitrate": "160k"
    },
    "command_preview": [
      "ffmpeg",
      "-i",
      "https://example.com/manifest.mpd",
      "-i",
      "https://example.com/subtitles.vtt"
    ],
    "would_create_job": false
  }
}
```

### API: GET /jobs

```yaml
path: /jobs
method: GET
authentication: required
headers:
  Authorization: Bearer <access_token>
query_parameters:
  state: optional job state filter
request_body: null
response_body:
  status: success
  body: array of job objects
status_codes:
  200: Jobs returned.
  401: Missing or invalid bearer token.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8090/jobs?state=queued
```

Example response:

```json
{
  "status": "success",
  "body": []
}
```

### API: GET /jobs/{uid}

```yaml
path: /jobs/{uid}
method: GET
authentication: required
headers:
  Authorization: Bearer <access_token>
path_parameters:
  uid: job uid
request_body: null
response_body:
  status: success
  body: job object
status_codes:
  200: Job returned.
  401: Missing or invalid bearer token.
  404: Job was not found.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8090/jobs/Ab8XsAhPkzky5Gys
```

Example response:

```json
{
  "status": "success",
  "body": {
    "uid": "Ab8XsAhPkzky5Gys",
    "state": "queued",
    "source_user_agent": "MyClient/1.0",
    "target_filename": "Example Show - S01E02.mp4"
  }
}
```

### API: GET /jobs/{uid}/events

```yaml
path: /jobs/{uid}/events
method: GET
authentication: required
headers:
  Authorization: Bearer <access_token>
path_parameters:
  uid: job uid
request_body: null
response_body:
  status: success
  body:
    - uid: string
      job_uid: string
      event_type: string
      message: string
      payload: object
      created_at: integer
status_codes:
  200: Job events returned.
  401: Missing or invalid bearer token.
  404: Job was not found.
  500: Unexpected server error.
error_response:
  status: error
  message: Human readable error
```

Example request:

```cmd
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8090/jobs/Ab8XsAhPkzky5Gys/events
```

Example response:

```json
{
  "status": "success",
  "body": [
    {
      "uid": "eventUid",
      "job_uid": "Ab8XsAhPkzky5Gys",
      "event_type": "running",
      "message": "Job started",
      "payload": {},
      "created_at": 1779169008
    }
  ]
}
```

### API: PATCH /jobs/{uid}

```yaml
path: /jobs/{uid}
method: PATCH
authentication: required
headers:
  Authorization: Bearer <access_token>
  Content-Type: application/json
path_parameters:
  uid: job uid
request_body:
  source_url: string, optional
  subtitles_url: string, optional
  output_title: string, optional
  title: string, optional
  season: integer, optional
  episode: integer, optional
  selected_streams: object, optional
  encoder_options: object, optional
response_body:
  status: success
  body: job object
status_codes:
  200: Job updated.
  400: Job cannot be updated in its current state.
  401: Missing or invalid bearer token.
  404: Job was not found.
```

Only `queued`, `failed`, and `cancelled` jobs can be patched.

### API: POST /jobs/{uid}/cancel

```yaml
path: /jobs/{uid}/cancel
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
path_parameters:
  uid: job uid
request_body: null
response_body:
  status: success
  body: job object
status_codes:
  200: Cancellation accepted.
  400: Job cannot be cancelled in its current state.
  401: Missing or invalid bearer token.
  404: Job was not found.
```

Queued jobs move directly to `cancelled`. Running jobs move to `cancel_requested`; the worker terminates the active `ffmpeg` process and then marks the job `cancelled`.

### API: POST /jobs/{uid}/retry

```yaml
path: /jobs/{uid}/retry
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
  Content-Type: application/json
path_parameters:
  uid: job uid
request_body:
  source_url: string, optional
  subtitles_url: string, optional
  output_title: string, optional
  title: string, optional
  season: integer, optional
  episode: integer, optional
  selected_streams: object, optional
  encoder_options: object, optional
response_body:
  status: success
  body: job object
status_codes:
  200: Job queued for retry.
  400: Job cannot be retried in its current state.
  401: Missing or invalid bearer token.
  404: Job was not found.
```

Only `failed` and `cancelled` jobs can be retried.

### API: GET /queue/status

```yaml
path: /queue/status
method: GET
authentication: required
headers:
  Authorization: Bearer <access_token>
request_body: null
response_body:
  status: success
  body:
    paused: boolean
    running_jobs: array of job uid strings
status_codes:
  200: Queue status returned.
  401: Missing or invalid bearer token.
```

### API: POST /queue/pause

```yaml
path: /queue/pause
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
request_body: null
response_body:
  status: success
  body:
    paused: true
    running_jobs: array of job uid strings
status_codes:
  200: Queue paused.
  401: Missing or invalid bearer token.
```

Pause prevents the worker from claiming new jobs. It does not stop already running jobs.

### API: POST /queue/resume

```yaml
path: /queue/resume
method: POST
authentication: required
headers:
  Authorization: Bearer <access_token>
request_body: null
response_body:
  status: success
  body:
    paused: false
    running_jobs: array of job uid strings
status_codes:
  200: Queue resumed.
  401: Missing or invalid bearer token.
```

### Worker Behavior

When `WORKER_ENABLED` is true, the backend starts a background worker during application startup. The worker:

- claims `queued` jobs up to `MAX_CONCURRENT_JOBS`
- writes temporary output to `WORK_DIR`
- probes media duration with `ffprobe` when possible
- runs `ffmpeg` with `-progress pipe:1`
- uses per-job `source_user_agent` when present, otherwise falls back to default headers
- updates `processed_time`, `speed`, `current_phase`, and `progress_percent`
- appends job events for command start, completion, and failure
- moves successful files into the job `target_path` inside `PLEX_MEDIA_ROOT`
- marks jobs left in `running` or `cancel_requested` as `failed` on worker restart
- removes temporary output after cancellation or failed `ffmpeg` execution
- terminates active `ffmpeg` processes first, then kills them after `PROCESS_TERMINATE_TIMEOUT`

No Plex HTTP API calls are made. Plex integration is limited to deterministic file placement inside the configured Plex media folder.

## Operational Deployment

Recommended Linux layout:

```text
/opt/alloha/app        Repository checkout
/opt/alloha/work       Temporary worker files
/var/log/alloha        Application logs
/media                 Plex media root, or the mounted library root used by Plex
```

Create runtime directories and grant write access to the service user:

```bash
sudo mkdir -p /opt/alloha/work /var/log/alloha /media
sudo chown -R alloha:alloha /opt/alloha /var/log/alloha /media
```

Install and verify dependencies:

```bash
uv sync
ffmpeg -version
uv run alembic heads
uv run alembic upgrade head
```

Before each startup after model changes, generate and apply the Alembic migration:

```bash
uv run alembic revision --autogenerate -m "describe change"
uv run alembic upgrade head
```

Example `systemd` service:

```ini
[Unit]
Description=Alloha Downloader Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=alloha
Group=alloha
WorkingDirectory=/opt/alloha/app
Environment=DB_URL=mysql+aiomysql://alloha:change-me@127.0.0.1:3306/alloha
Environment=SECRET_KEY=change-this-secret
ExecStartPre=/usr/bin/env uv run alembic upgrade head
ExecStart=/usr/bin/env uv run python -m backend
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Health check:

```bash
curl http://127.0.0.1:8090/health
```

Docker example:

```bash
cp docker-compose.example.yml docker-compose.yml
docker compose --profile ops run --rm alloha-migrate
docker compose up -d
```

Set at least:

```text
DB_URL=mysql+aiomysql://alloha:change-me@db:3306/alloha
SECRET_KEY=change-this-secret
```

When running in containers, mount persistent host paths for `WORK_DIR`, `PLEX_MEDIA_ROOT`, and logs.
Run migrations before starting the backend container so normal app startup only launches the server.

Log rotation example:

```text
/var/log/alloha/*.log {
  daily
  rotate 14
  compress
  missingok
  notifempty
  copytruncate
}
```

Backup notes:

- Back up the external database according to your MySQL/MariaDB backup policy.
- Back up `backend/config/settings.yaml` separately from secrets stored in the environment.
- Completed media is already in the Plex media root and should follow the server media backup policy.

Common deployment errors:

- `ffmpeg` is not found: install `ffmpeg` or set `FFMPEG_BINARY` to the executable path.
- worker cannot write temp files: create `WORK_DIR` and grant write access to the service user.
- completed files cannot be moved: mount `PLEX_MEDIA_ROOT` and grant write access.
- database startup fails: set `DB_URL` for both Alembic and application startup.
- `401 Invalid token`: send a JWT access token signed with `SECRET_KEY`.

## Tests

Run the test suite:

```cmd
uv run pytest
```

Current tests cover:

- ffmpeg command generation
- ffmpeg progress parsing
- Plex target path generation
- job state transition rules
- JWT protection on queue endpoints

The worker tests do not download real media. Future worker process tests should use a mocked `ffmpeg` executable or a short local fixture.

## Usage

Run with the sample URLs embedded in `main.py`:

```cmd
uv run python main.py
```

Run with explicit DASH and subtitle URLs:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" -o output.mp4
```

Create a short test encode:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" -o sample.mp4 --duration 00:00:10
```

Set the output video title metadata:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" -o output.mp4 --title "FBI International S01E14"
```

Disable proxy explicitly:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" --proxy ""
```

Use another proxy:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" --proxy "http://127.0.0.1:8080"
```

## Arguments

```text
source_url              DASH source URL. Optional; defaults to the URL in main.py.
subtitles_url           WebVTT subtitles URL. Optional; defaults to the URL in main.py.
-o, --output            Output MP4 path. Defaults to FBI_International.S01E14.mp4.
--proxy                 HTTP proxy passed to ffmpeg. Defaults to VIDEO_PROXY, then 127.0.0.1:10809 if running, then HTTPS_PROXY.
--video-stream          ffmpeg video stream selector. Defaults to 0:v:1.
--audio-stream          ffmpeg audio stream selector. Defaults to 0:a:1.
--subtitle-stream       ffmpeg subtitle stream selector. Defaults to 1:0.
--crf                   Video quality value passed to ffmpeg. Defaults to 18.
--preset                Encoder preset. Defaults to slow.
--title                 Optional output metadata title.
--duration              Optional test duration, such as 5 or 00:00:05.
```

## Environment Variables

```text
VIDEO_PROXY       Overrides the proxy auto-detection.
HTTPS_PROXY       Used only when VIDEO_PROXY is not set and the default local proxy is unavailable.
VIDEO_STREAM      Overrides the default video stream selector.
AUDIO_STREAM      Overrides the default audio stream selector.
SUBTITLE_STREAM   Overrides the default subtitle stream selector.
CRF               Overrides the default CRF value.
PRESET            Overrides the default encoder preset.
COOKIE            Adds a Cookie header to both ffmpeg inputs.
```

cmd example:

```cmd
set "VIDEO_PROXY=http://127.0.0.1:10809"
set "COOKIE=name=value; another=value"
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" -o output.mp4
```

## Finding URLs and Headers

The `browser/` directory contains captured request examples:

- `browser/headers.txt` shows a DASH manifest request.
- `browser/incoming_chunk_headers.txt` shows a media chunk request through a local proxy.

To use the script with another video:

1. Open the page in a browser.
2. Open developer tools and inspect the Network tab.
3. Find the DASH manifest request, usually an MPD or DASH XML response.
4. Find the WebVTT subtitles request, usually a `.vtt` URL.
5. Pass both URLs to `main.py`.

The script sends browser-like `Origin`, `Referer`, `User-Agent`, and client-hint headers from `main.py`. If a site requires a session, pass the current cookie through the `COOKIE` environment variable.

## Stream Selection

The defaults are:

```text
video:     0:v:1
audio:     0:a:1
subtitles: 1:0
```

If the output has the wrong video quality, audio track, or subtitle track, inspect available streams with `ffprobe` or run `ffmpeg` manually against the same inputs, then override the selectors:

```cmd
uv run python main.py "https://example.com/path/manifest.mpd" "https://example.com/path/subtitles.vtt" ^
  --video-stream 0:v:0 ^
  --audio-stream 0:a:0 ^
  --subtitle-stream 1:0 ^
  -o output.mp4
```

## Output

The generated MP4 uses:

- HEVC video via `hevc_nvenc`
- AAC audio at 160 kbps
- `mov_text` subtitles for MP4 compatibility
- `+faststart` so playback can begin before the whole file is downloaded

## Troubleshooting

- `ffmpeg` is not recognized: install `ffmpeg` and add it to `PATH`.
- `Unknown encoder 'hevc_nvenc'`: install an NVIDIA driver with NVENC support, use a machine with compatible NVIDIA hardware, or change the encoder in `main.py`.
- Chunk requests fail directly: run a local proxy and pass it with `--proxy`, or set `VIDEO_PROXY`.
- HTTP 403 or empty output: refresh the source/subtitle URLs and cookie from the browser; these URLs often expire.
- Wrong language or quality: override `--video-stream`, `--audio-stream`, or `--subtitle-stream`.
