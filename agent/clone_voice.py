"""
Clone the artist's voice on ElevenLabs — run once before the demo.

Usage:
  python clone_voice.py --audio JK_v1.m4a --name "JK_v1"
  python clone_voice.py --list

ElevenLabs requirements:
  - Minimum ~1 minute of audio (longer = better clone quality)
  - Clean audio: no background music, crowd noise, or reverb
  - Supported formats: mp3, wav, m4a, ogg, flac
"""

import argparse
import asyncio
import os
import sys
import httpx
from dotenv import load_dotenv

load_dotenv()


async def clone(audio_path: str, name: str, api_key: str) -> str:
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    size_mb = len(audio_bytes) / 1024 / 1024
    print(f"File size: {size_mb:.2f} MB")

    if size_mb < 0.3:
        print("\n⚠️  Warning: audio is very short. ElevenLabs needs at least ~1 minute.")
        print("   For best results use 1–5 minutes of clean speech.")
        print("   Continuing anyway...\n")

    filename = os.path.basename(audio_path)
    ext = filename.rsplit(".", 1)[-1].lower()
    mime = {
        "mp3": "audio/mpeg",
        "wav": "audio/wav",
        "m4a": "audio/mp4",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "webm": "audio/webm",
    }.get(ext, "audio/mpeg")

    print(f"Uploading as {mime}...")

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            "https://api.elevenlabs.io/v1/voices/add",
            headers={"xi-api-key": api_key},
            data={
                "name": name,
                "description": f"VoiceBridge cloned voice: {name}",
            },
            files={"files": (filename, audio_bytes, mime)},
        )

        if not resp.is_success:
            # Print the actual error body so we know what went wrong
            try:
                err = resp.json()
                detail = err.get("detail", {})
                if isinstance(detail, dict):
                    msg = detail.get("message", str(detail))
                else:
                    msg = str(detail)
            except Exception:
                msg = resp.text

            print(f"\n❌  ElevenLabs error ({resp.status_code}): {msg}")

            if resp.status_code == 400:
                print("\nCommon causes:")
                print("  • Audio too short — ElevenLabs needs at least 1 minute")
                print("  • Audio quality too low — use a cleaner recording")
                print("  • Free plan limit reached — check your ElevenLabs quota")
                print("\nTip: Get a longer clip. A YouTube interview works well.")
                print("     Download with: yt-dlp -x --audio-format mp3 'URL' -o artist.mp3")
            sys.exit(1)

        voice_id = resp.json()["voice_id"]
        return voice_id


async def list_voices(api_key: str):
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key},
        )
        resp.raise_for_status()
        return resp.json()["voices"]


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", help="Path to audio file (mp3, m4a, wav)")
    ap.add_argument("--name",  help="Voice name, e.g. 'JK_v1'")
    ap.add_argument("--list",  action="store_true", help="List existing cloned voices")
    args = ap.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not set in .env")
        sys.exit(1)

    if args.list:
        voices = await list_voices(api_key)
        if not voices:
            print("No cloned voices found.")
        else:
            print(f"\n{'Voice ID':<30} {'Name'}")
            print("-" * 55)
            for v in voices:
                print(f"{v['voice_id']:<30} {v['name']}")
        return

    if not args.audio or not args.name:
        print("Usage: python clone_voice.py --audio FILE --name NAME")
        sys.exit(1)

    if not os.path.exists(args.audio):
        print(f"File not found: {args.audio}")
        sys.exit(1)

    print(f"Cloning voice from: {args.audio}")
    print("This takes 30–60 seconds...\n")

    voice_id = await clone(args.audio, args.name, api_key)

    print(f"\n✅  Voice cloned successfully!")
    print(f"\n   Add this to your .env file:")
    print(f"   ARTIST_VOICE_ID={voice_id}")


if __name__ == "__main__":
    asyncio.run(main())
