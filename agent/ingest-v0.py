"""
VoiceBridge Stream Ingestor
----------------------------
Pulls audio from a YouTube stream (or any local file) and
publishes it as the "artist" track into a LiveKit room.

Usage:
  # YouTube live stream
  python ingest.py --url "https://youtube.com/watch?v=LIVE_ID" --room concert-live

  # Local audio file (great for hackathon demo)
  python ingest.py --url "./artist_clip.mp3" --room concert-live

  # Get a token manually and pass it
  python ingest.py --url "..." --room concert-live --token "eyJ..."

Requires: pip install yt-dlp (+ ffmpeg on system: brew install ffmpeg)
"""

import argparse
import asyncio
import logging
import os
import subprocess

import httpx
import numpy as np
from dotenv import load_dotenv
from livekit import rtc

load_dotenv()
logger = logging.getLogger("voicebridge.ingest")
logging.basicConfig(level=logging.INFO)

SAMPLE_RATE    = 48000
CHANNELS       = 1
FRAME_SAMPLES  = SAMPLE_RATE // 10   # 100ms frames
FRAME_BYTES    = FRAME_SAMPLES * CHANNELS * 2


async def get_token(server_url: str, room: str, identity: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{server_url}/token",
            params={"room": room, "identity": identity, "role": "artist"},
        )
        r.raise_for_status()
        d = r.json()
        return d["token"], d["livekit_url"]


async def publish(url: str, livekit_url: str, token: str, room_name: str):
    room   = rtc.Room()
    source = rtc.AudioSource(SAMPLE_RATE, CHANNELS)
    track  = rtc.LocalAudioTrack.create_audio_track("artist-audio", source)

    await room.connect(livekit_url, token)
    logger.info(f"Connected to LiveKit room: {room_name}")

    await room.local_participant.publish_track(
        track,
        rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
    )
    logger.info("Artist audio track published")

    # yt-dlp handles both URLs and local files
    is_local = not url.startswith("http")

    if is_local:
        # Local file: pipe directly through ffmpeg
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet", "-i", url,
             "-vn", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE),
             "-ac", str(CHANNELS), "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        reader = ffmpeg.stdout
    else:
        # Remote stream: yt-dlp → ffmpeg
        ytdlp = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio", "-o", "-", "--quiet", url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
             "-vn", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE),
             "-ac", str(CHANNELS), "-f", "s16le", "pipe:1"],
            stdin=ytdlp.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        reader = ffmpeg.stdout

    logger.info(f"Streaming: {url}")

    try:
        while True:
            raw = reader.read(FRAME_BYTES)
            if not raw:
                break
            if len(raw) < FRAME_BYTES:
                raw += b"\x00" * (FRAME_BYTES - len(raw))

            frame = rtc.AudioFrame(
                data=np.frombuffer(raw, dtype=np.int16).tobytes(),
                sample_rate=SAMPLE_RATE,
                num_channels=CHANNELS,
                samples_per_channel=FRAME_SAMPLES,
            )
            await source.capture_frame(frame)

    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        if not is_local:
            ytdlp.terminate()
        ffmpeg.terminate()
        await room.disconnect()
        logger.info("Disconnected from LiveKit")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url",        required=True,  help="YouTube URL or local audio file path")
    ap.add_argument("--room",       default="concert-live")
    ap.add_argument("--identity",   default="artist-stream")
    ap.add_argument("--server",     default="http://localhost:8080", help="Token server URL")
    ap.add_argument("--token",      default=None, help="Pass token directly (skips server)")
    ap.add_argument("--livekit-url",default=None)
    args = ap.parse_args()

    if args.token:
        token       = args.token
        livekit_url = args.livekit_url or os.environ["LIVEKIT_URL"]
    else:
        logger.info(f"Fetching token from {args.server}...")
        token, livekit_url = await get_token(args.server, args.room, args.identity)

    await publish(args.url, livekit_url, token, args.room)


if __name__ == "__main__":
    asyncio.run(main())
