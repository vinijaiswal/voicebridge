"""
VoiceBridge Stream Ingestor
----------------------------
Publishes audio into a LiveKit room as the artist track.

Usage:
  python ingest.py --url ./JK_v1.m4a --room concert-live
  python ingest.py --url ./JK_v1.m4a --room concert-live --loop 5
  python ingest.py --url "https://youtube.com/watch?v=ID" --room concert-live
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

SAMPLE_RATE   = 48000
CHANNELS      = 1
FRAME_SAMPLES = SAMPLE_RATE // 10    # 100ms frames
FRAME_BYTES   = FRAME_SAMPLES * CHANNELS * 2


async def get_token(server_url: str, room: str, identity: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{server_url}/token",
            params={"room": room, "identity": identity, "role": "artist"},
        )
        r.raise_for_status()
        d = r.json()
        return d["token"], d["livekit_url"]


def open_ffmpeg(url: str):
    """Open an ffmpeg process that outputs raw PCM s16le to stdout."""
    is_local = not url.startswith("http")

    if is_local:
        proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet",
             "-i", url,
             "-vn", "-acodec", "pcm_s16le",
             "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
             "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        return proc, None
    else:
        ytdlp = subprocess.Popen(
            ["yt-dlp", "-f", "bestaudio", "-o", "-", "--quiet", url],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        ffmpeg = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet",
             "-i", "pipe:0",
             "-vn", "-acodec", "pcm_s16le",
             "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
             "-f", "s16le", "pipe:1"],
            stdin=ytdlp.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        return ffmpeg, ytdlp


async def stream_audio(source: rtc.AudioSource, url: str, loops: int):
    total = 0
    for loop_i in range(loops):
        if loops > 1:
            logger.info(f"Loop {loop_i + 1}/{loops}: streaming {url}")
        else:
            logger.info(f"Streaming: {url}")

        ffmpeg, ytdlp = open_ffmpeg(url)

        try:
            while True:
                raw = ffmpeg.stdout.read(FRAME_BYTES)
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
                total += 1
        finally:
            ffmpeg.terminate()
            if ytdlp:
                ytdlp.terminate()

        if loop_i < loops - 1:
            logger.info("Loop complete, replaying...")
            await asyncio.sleep(0.5)

    logger.info(f"Done — streamed {total} frames total")


async def publish(url: str, livekit_url: str, token: str, room_name: str, loops: int):
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

    try:
        await stream_audio(source, url, loops)
    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        await room.disconnect()
        logger.info("Disconnected from LiveKit")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url",         required=True,  help="Local file or YouTube URL")
    ap.add_argument("--room",        default="concert-live")
    ap.add_argument("--identity",    default="artist-stream")
    ap.add_argument("--server",      default="http://localhost:8080")
    ap.add_argument("--token",       default=None)
    ap.add_argument("--livekit-url", default=None)
    ap.add_argument("--loop",        type=int, default=1, help="How many times to loop the file (default: 1)")
    args = ap.parse_args()

    if args.token:
        token       = args.token
        livekit_url = args.livekit_url or os.environ["LIVEKIT_URL"]
    else:
        logger.info(f"Fetching token from {args.server}...")
        token, livekit_url = await get_token(args.server, args.room, args.identity)

    await publish(args.url, livekit_url, token, args.room, args.loop)


if __name__ == "__main__":
    asyncio.run(main())
