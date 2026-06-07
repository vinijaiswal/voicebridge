# VoiceBridge 🌐

Real-time voice translation that speaks in the artist's cloned voice.
Korean → English in the artist's actual voice, live.

```
Artist stream → LiveKit → Whisper STT → GPT-4o → ElevenLabs (cloned voice) → Fan hears English
```

---

## Setup (15 minutes)

### 1. Get your accounts and keys

| Service | What for | Link |
|---------|----------|------|
| LiveKit Cloud (free) | Audio room backbone | https://cloud.livekit.io |
| OpenAI | Whisper STT + GPT-4o translation | https://platform.openai.com/api-keys |
| ElevenLabs (free tier) | Voice cloning + TTS | https://elevenlabs.io |

### 2. Configure .env

```bash
cd agent
cp .env.example .env
# Fill in your keys
```

### 3. Clone the artist's voice (one-time, ~2 min)

Get 1–3 minutes of clean audio of the artist speaking.
Interviews or acoustic performances work best — avoid crowd noise.

```bash
cd agent
python clone_voice.py --audio artist_sample.mp3 --name "my-artist"

# Output: ARTIST_VOICE_ID=xxxxxxxxxxxx
# Paste that into your .env
```

To list voices you've already cloned:
```bash
python clone_voice.py --list
```

### 4. Start everything

```bash
chmod +x start.sh
./start.sh
```

This starts the token server and translation agent in one shot.

### 5. Ingest the artist's stream

```bash
# YouTube live stream
cd agent && python ingest.py --url "https://youtube.com/watch?v=LIVE_ID" --room concert-live

# Local file (recommended for hackathon demo — more reliable)
cd agent && python ingest.py --url ./artist_clip.mp3 --room concert-live

# Or start everything + ingest in one command
./start.sh --stream "https://youtube.com/watch?v=LIVE_ID"
```

### 6. Open the fan page

Open `frontend/index.html` in a browser.
- Token server: `http://localhost:8080`
- Room: `concert-live`
- Hit **Join live translation**

You'll hear the artist's Korean speech come back in English — in their own cloned voice.

---

## How it works

```
ingest.py          Pulls audio from YouTube/file via yt-dlp + ffmpeg
    ↓              Publishes as "artist" audio track into LiveKit room
LiveKit room       WebRTC audio backbone, sub-50ms transport
    ↓
agent.py           Subscribes to artist track
    ↓              Silero VAD detects speech boundaries
    ↓              Sends chunk to OpenAI Whisper (Korean STT)
    ↓              Sends transcript to GPT-4o (translation)
    ↓              Sends English text to ElevenLabs (cloned voice TTS)
    ↓              Publishes translated audio back into LiveKit room
fan browser        Subscribes to translated audio track
                   Hears English in artist's voice with ~2–4s lag
```

## Latency breakdown

| Step | Typical |
|------|---------|
| LiveKit transport | ~50ms |
| Silero VAD (endpointing) | ~300–500ms |
| Whisper STT | ~400–700ms |
| GPT-4o translation | ~300–500ms |
| ElevenLabs TTS | ~800–1500ms |
| **Total** | **~2–3 seconds** |

---

## Project structure

```
voicebridge/
├── agent/
│   ├── agent.py          # LiveKit agent — STT → translate → TTS loop
│   ├── server.py         # Token server (FastAPI)
│   ├── ingest.py         # Stream ingestor (YouTube → LiveKit)
│   ├── clone_voice.py    # One-time ElevenLabs voice cloning
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── index.html        # Fan web app
└── start.sh              # One-command launcher
```

---

## Hackathon demo tips

1. **Use a local file, not live YouTube** — feed a downloaded Korean clip through `ingest.py`. It looks identical to a live stream from the fan's perspective but eliminates network risk mid-demo.

2. **Clone the voice the night before** — ElevenLabs cloning takes ~60 seconds but you don't want to do it on stage.

3. **Show the latency** — the fan page shows live phrase count and latency. Real numbers in a demo always land well with judges.

4. **The demo moment** — play a 30-second Korean clip, let the room go quiet, then the English comes back in the same voice. That's your applause moment.
