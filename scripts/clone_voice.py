"""
VoiceBridge — Voice Cloning Setup
-----------------------------------
Run this ONCE before the hackathon to clone the artist's voice on MiniMax.
Point it at any clean audio file of the artist (1–5 minutes recommended).

Usage:
  python clone_voice.py --audio ./artist_sample.mp3 --name "my-artist"

Output:
  Prints the ARTIST_VOICE_ID to paste into your .env file.

Tips for best results:
  - Use audio where the artist is speaking clearly (interview, acoustic performance)
  - Avoid background music, crowd noise, heavy reverb
  - 2-3 minutes is the sweet spot
  - Multiple shorter clips are fine too — just concatenate them first with ffmpeg:
      ffmpeg -i clip1.mp3 -i clip2.mp3 -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1" combined.mp3
"""

import argparse
import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/agent")
from minimax_client import MinimaxClient


async def main():
    parser = argparse.ArgumentParser(description="Clone artist voice on MiniMax")
    parser.add_argument("--audio", required=True,  help="Path to audio file (MP3 or WAV)")
    parser.add_argument("--name",  required=True,  help="Voice name, e.g. 'my-artist-vocals'")
    parser.add_argument("--list",  action="store_true", help="List existing cloned voices")
    args = parser.parse_args()

    api_key  = os.environ["MINIMAX_API_KEY"]
    group_id = os.environ["MINIMAX_GROUP_ID"]
    client   = MinimaxClient(api_key, group_id)

    if args.list:
        voices = await client.list_voices()
        if not voices:
            print("No cloned voices found.")
        else:
            print(f"\n{'Voice ID':<40} {'Name':<30} {'Status'}")
            print("-" * 80)
            for v in voices:
                print(f"{v.get('voice_id',''):<40} {v.get('name',''):<30} {v.get('status','')}")
        await client.close()
        return

    if not os.path.exists(args.audio):
        print(f"Error: audio file not found: {args.audio}")
        sys.exit(1)

    file_size_mb = os.path.getsize(args.audio) / (1024 * 1024)
    print(f"Audio file: {args.audio} ({file_size_mb:.1f} MB)")
    print(f"Voice name: {args.name}")
    print("Uploading to MiniMax for voice cloning... (this may take 30-60 seconds)")

    try:
        voice_id = await client.clone_voice(args.audio, args.name)
        print(f"\n✓ Voice cloned successfully!")
        print(f"\n  Voice ID: {voice_id}")
        print(f"\n  Add this to your .env file:")
        print(f"  ARTIST_VOICE_ID={voice_id}")
    except Exception as e:
        print(f"\n✗ Error cloning voice: {e}")
        sys.exit(1)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
