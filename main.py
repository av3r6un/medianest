import argparse
import os
import socket
import subprocess
from pathlib import Path


DEFAULT_SOURCE_URL = (
    "https://hye1eaipby4w.interkh.com/x-en-x/"
    "khw0RhQ2Ya8ckX8aRp8xRn8ckC9NybJLy0JOya84kvE2RGRuMWlwj2ZZjBQ5RiL5RhSeSvQ4"
    "Srz0RCSfzG1eShsekhbxRrbGSvQxzmRrHiw9zrkeRhOeRhE3k2swFiR3OrZGjBX2qvl4biSF"
    "kifrHtA9FBZek2E1RGRaFiLcRBD5OrZ1jBZeRBepz2b4zBA3Rib0kpSfKmw9SBA2ShXek2Ovk"
    "rspRvqxOoA9RBq3FBb3khR4FnS2qhL="
)
DEFAULT_SUBTITLES_URL = (
    "https://hye1eaipby4w.interkh.com/04_10_22/04/10/23/6OUVHHM7/RZG4SWUZ.vtt"
    "?ha=890b906ef88ff40&hc=ed4e4512e3f81ac&hi=bce02e0177dd8c7&hs=1vr0xPfN4j"
    "&ht=98e7a53328b0109&hu=8e19bce8a470e46&t=1779574389"
)

DEFAULT_OUTPUT_FILE = Path("FBI_International.S01E14.mp4")
DEFAULT_PROXY = "http://127.0.0.1:10809"

DEFAULT_HEADERS = (
    "Accept: */*\r\n"
    "Accept-Language: en-GB,en;q=0.9\r\n"
    "Origin: https://fbr-lordfilms.ru\r\n"
    "Referer: https://fbr-lordfilms.ru/\r\n"
    "Sec-Fetch-Dest: empty\r\n"
    "Sec-Fetch-Mode: cors\r\n"
    "Sec-Fetch-Site: cross-site\r\n"
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) Gecko/20100101 Firefox/151.0\r\n"
)


def local_proxy_is_running(proxy_url: str) -> bool:
    if not proxy_url.startswith("http://127.0.0.1:"):
        return True

    port_text = proxy_url.rsplit(":", 1)[-1].rstrip("/")
    try:
        port = int(port_text)
    except ValueError:
        return True

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def default_proxy() -> str:
    explicit_proxy = os.environ.get("VIDEO_PROXY")
    if explicit_proxy:
        return explicit_proxy if local_proxy_is_running(explicit_proxy) else ""

    if local_proxy_is_running(DEFAULT_PROXY):
        return DEFAULT_PROXY

    env_proxy = os.environ.get("HTTPS_PROXY")
    return env_proxy if env_proxy and local_proxy_is_running(env_proxy) else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a DASH source URL and WebVTT subtitles URL into an MP4."
    )
    parser.add_argument("source_url", nargs="?", default=DEFAULT_SOURCE_URL)
    parser.add_argument("subtitles_url", nargs="?", default=DEFAULT_SUBTITLES_URL)
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT_FILE))
    parser.add_argument("--proxy", default=default_proxy())
    parser.add_argument("--video-stream", default=os.environ.get("VIDEO_STREAM", "0:v:1"))
    parser.add_argument("--audio-stream", default=os.environ.get("AUDIO_STREAM", "0:a:1"))
    parser.add_argument("--subtitle-stream", default=os.environ.get("SUBTITLE_STREAM", "1:0"))
    parser.add_argument("--crf", default=os.environ.get("CRF", "18"))
    parser.add_argument("--preset", default=os.environ.get("PRESET", "slow"))
    parser.add_argument("--title", help="Optional output metadata title.")
    parser.add_argument("--duration", help="Optional test duration, for example 5 or 00:00:05.")
    return parser.parse_args()


def build_headers() -> str:
    cookie = os.environ.get("COOKIE")
    if cookie:
        return DEFAULT_HEADERS + f"Cookie: {cookie}\r\n"
    return DEFAULT_HEADERS


def input_options(headers: str, proxy: str) -> list[str]:
    options = [
        "-protocol_whitelist",
        "file,http,https,tcp,tls,httpproxy",
        "-headers",
        headers,
        "-rw_timeout",
        "15000000",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
    ]
    if proxy:
        options[0:0] = ["-http_proxy", proxy]
    return options


def build_command(args: argparse.Namespace) -> list[str]:
    headers = build_headers()
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-y",
        *input_options(headers, args.proxy),
        "-i",
        args.source_url,
        *input_options(headers, args.proxy),
        "-i",
        args.subtitles_url,
        "-map",
        args.video_stream,
        "-map",
        args.audio_stream,
        "-map",
        args.subtitle_stream,
        "-c:v",
        "hevc_nvenc",
        "-preset",
        args.preset,
        "-crf",
        args.crf,
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-c:s",
        "mov_text",
        "-metadata:s:a:0",
        "language=eng",
        "-metadata:s:s:0",
        "language=eng",
        "-disposition:s:0",
        "default",
        "-movflags",
        "+faststart",
        *(["-metadata", f"title={args.title}"] if args.title else []),
        *(["-t", args.duration] if args.duration else []),
        args.output,
    ]


def main() -> int:
    args = parse_args()

    command = build_command(args)

    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
