"""
MiniMax API Client
------------------
Handles all three pipeline steps:
  1. Speech-to-text  (T2A / ASR endpoint)
  2. Translation     (via ChatCompletion)
  3. TTS with voice  (T2A v2 with cloned voice)
"""

import asyncio
import base64
import logging
import httpx

logger = logging.getLogger("voicebridge.minimax")

MINIMAX_BASE = "https://api.minimax.chat/v1"


class MinimaxClient:
    def __init__(self, api_key: str, group_id: str):
        self._api_key  = api_key
        self._group_id = group_id
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    # ── 1. Speech-to-Text ────────────────────────────────────────────────────

    async def transcribe(self, wav_bytes: bytes, language: str = "Korean") -> str:
        """
        Send raw WAV bytes to MiniMax ASR.
        Returns the transcribed text string.
        """
        audio_b64 = base64.b64encode(wav_bytes).decode()
        payload = {
            "model": "speech-01-turbo",
            "audio_file": audio_b64,
            "language_boost": self._language_code(language),
        }
        resp = await self._http.post(
            f"{MINIMAX_BASE}/speech/recognitions",
            params={"GroupId": self._group_id},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("base_resp", {}).get("status_code") != 0:
            raise RuntimeError(f"MiniMax STT error: {data}")

        # Extract full transcript from utterances
        utterances = data.get("utterances", [])
        text = " ".join(u.get("text", "") for u in utterances).strip()
        if not text:
            text = data.get("text", "")
        return text

    # ── 2. Translation ───────────────────────────────────────────────────────

    async def translate(
        self,
        text: str,
        source_language: str = "Korean",
        target_language: str = "English",
    ) -> str:
        """
        Translate text using MiniMax ChatCompletion (abab6.5s is fast & cheap).
        Returns translated string.
        """
        system_prompt = (
            f"You are a professional real-time translator. "
            f"Translate the following {source_language} text into natural, fluent {target_language}. "
            f"Preserve the speaker's energy, emotion, and tone. "
            f"Return ONLY the translated text — no explanations, no quotes."
        )
        payload = {
            "model": "abab6.5s-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": text},
            ],
            "max_tokens": 500,
            "temperature": 0.2,
        }
        resp = await self._http.post(
            f"{MINIMAX_BASE}/text/chatcompletion_v2",
            params={"GroupId": self._group_id},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("base_resp", {}).get("status_code") != 0:
            raise RuntimeError(f"MiniMax translate error: {data}")

        return data["choices"][0]["message"]["content"].strip()

    # ── 3. TTS with voice cloning ────────────────────────────────────────────

    async def synthesize(self, text: str, voice_id: str) -> bytes:
        """
        Convert text to speech using the artist's cloned voice.
        Returns raw MP3 bytes.

        voice_id: the ID from MiniMax Voice Cloning dashboard
                  (or use a built-in voice like "male-qn-qingse")
        """
        payload = {
            "model": "speech-02-hd",
            "text": text,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 24000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        resp = await self._http.post(
            f"{MINIMAX_BASE}/text_to_speech",
            params={"GroupId": self._group_id},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("base_resp", {}).get("status_code") != 0:
            raise RuntimeError(f"MiniMax TTS error: {data}")

        audio_b64 = data.get("audio_file", "")
        if not audio_b64:
            raise RuntimeError("MiniMax TTS: no audio_file in response")

        return base64.b64decode(audio_b64)

    # ── Voice cloning helpers ────────────────────────────────────────────────

    async def clone_voice(self, audio_file_path: str, voice_name: str) -> str:
        """
        Upload an audio sample to MiniMax and create a cloned voice.
        Returns the voice_id to store in ARTIST_VOICE_ID env var.

        audio_file_path: path to a clean MP3/WAV of the artist (1-5 min recommended)
        voice_name: a label like "bts-jungkook"
        """
        with open(audio_file_path, "rb") as f:
            audio_bytes = f.read()

        audio_b64 = base64.b64encode(audio_bytes).decode()
        payload = {
            "voice_id": voice_name.lower().replace(" ", "-"),
            "file": audio_b64,
            "need_noise_reduction": True,
            "need_volume_normalization": True,
            "accuracy": 3,         # 1-4, higher = more accurate but slower
        }

        # MiniMax voice cloning uses a multipart-style endpoint
        resp = await self._http.post(
            f"{MINIMAX_BASE}/voice_clone/create",
            params={"GroupId": self._group_id},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("base_resp", {}).get("status_code") != 0:
            raise RuntimeError(f"Voice clone error: {data}")

        voice_id = data.get("voice_id", voice_name.lower().replace(" ", "-"))
        logger.info(f"Voice cloned successfully. Voice ID: {voice_id}")
        return voice_id

    async def list_voices(self) -> list[dict]:
        """List all cloned voices in your MiniMax account."""
        resp = await self._http.get(
            f"{MINIMAX_BASE}/voice_clone/list",
            params={"GroupId": self._group_id},
        )
        resp.raise_for_status()
        return resp.json().get("voices", [])

    async def close(self):
        await self._http.aclose()

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _language_code(language: str) -> str:
        mapping = {
            "Korean": "ko",
            "Japanese": "ja",
            "Chinese": "zh",
            "English": "en",
            "Spanish": "es",
            "French": "fr",
        }
        return mapping.get(language, "ko")
