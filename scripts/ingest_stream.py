"""
VoiceBridge Stream Ingestor
----------------------------
Captures audio from a YouTube live stream (or any URL yt-dlp supports)
and publishes it as an audio track into a LiveKit room.

This is what runs "on behalf of the artist" — it pulls the stream audio
and makes it available to the translation agent inside LiveKit.

Usage:
  python ingest_stream.py --url "https://www.youtube.com/watch?v=LIVE_ID" \
                          --room concert-live \
                          --server-url http://localhost:8080

Requirements:
  pip install yt-dlp ffmpeg-python livekit
  Also needs ffmpeg installed on the system: brew install ffmpeg
"""

import argparse
import asyncio
import logging
import subprocess
import sys
import httpx
import numpy as np

from livekit import rtc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebridge.ingest")

SAMPLE_RATE  = 48000
NUM_CHANNELS = 1
CHUNK_MS     = 100          # publish 100ms frames to LiveKit
FRAME_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000


async def get_token(server_url: str, room: str, identity: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{server_url}/token/artist",
            params={"room": room, "identity": identity},
        )
        resp.raise_for_status()
        return resp.json()["token"]


async def ingest(stream_url: str, room_name: str, livekit_url: str, token: str):
    # Connect to LiveKit room
    room = rtc.Room()
    await room.connect(livekit_url, token)
    logger.info(f"Connected to LiveKit room: {room_name}")

    # Create and publish audio source
    source = rtc.AudioSource(sample_rate=SAMPLE_RATE, num_channels=NUM_CHANNELS)
    track  = rtc.LocalAudioTrack.create_audio_track("artist-audio", source)
    options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    await room.local_participant.publish_track(track, options)
    logger.info("Audio track published")

    # Start yt-dlp | ffmpeg pipeline
    # yt-dlp gets the stream URL, ffmpeg converts to raw PCM
    ytdlp_proc = subprocess.Popen(
        ["yt-dlp", "-f", "bestaudio", "-o", "-", "--quiet", stream_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    ffmpeg_proc = subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "quiet",
            "-i", "pipe:0",
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(SAMPLE_RATE),
            "-ac", str(NUM_CHANNELS),
            "-f", "s16le",
            "pipe:1",
        ],
        stdin=ytdlp_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    logger.info(f"Streaming from: {stream_url}")

    bytes_per_frame = FRAME_SAMPLES * NUM_CHANNELS * 2  # 16-bit = 2 bytes

    try:
        while True:
            raw = ffmpeg_proc.stdout.read(bytes_per_frame)
            if not raw:
                logger.info("Stream ended")
                break

            # Pad last frame if needed
            if len(raw) < bytes_per_frame:
                raw = raw + b'\x00' * (bytes_per_frame - len(raw))

            audio_data = np.frombuffer(raw, dtype=np.int16)
            frame = rtc.AudioFrame(
                data=audio_data.tobytes(),
                sample_rate=SAMPLE_RATE,
                num_channels=NUM_CHANNELS,
                samples_per_channel=FRAME_SAMPLES,
            )
            await source.capture_frame(frame)

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        ytdlp_proc.terminate()
        ffmpeg_proc.terminate()
        await room.disconnect()
        logger.info("Disconnected from LiveKit")


async def main():
    parser = argparse.ArgumentParser(description="VoiceBridge Stream Ingestor")
    parser.add_argument("--url",        required=True,  help="YouTube or stream URL")
    parser.add_argument("--room",       default="concert-live", help="LiveKit room name")
    parser.add_argument("--identity",   default="artist-stream", help="Publisher identity")
    parser.add_argument("--server-url", default="http://localhost:8080", help="Token server URL")
    parser.add_argument("--livekit-url", default=None, help="LiveKit server URL (overrides .env)")
    args = parser.parse_args()

    import os
    from dotenv import load_dotenv
    load_dotenv()

    livekit_url = args.livekit_url or os.environ.get("LIVEKIT_URL", "ws://localhost:7880")

    logger.info(f"Getting token from {args.server_url}...")
    token = await get_token(args.server_url, args.room, args.identity)

    await ingest(args.url, args.room, livekit_url, token)


if __name__ == "__main__":
    asyncio.run(main())
