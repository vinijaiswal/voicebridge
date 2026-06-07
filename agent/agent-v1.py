"""
VoiceBridge Agent — LiveKit Agents 1.0
----------------------------------------
Uses AgentSession (the unified v1.0 orchestrator) to:
  1. Listen to the artist's audio track via Silero VAD
  2. Transcribe Korean with OpenAI Whisper (STT)
  3. Translate Korean → English with GPT-4o (LLM)
  4. Speak English in the cloned voice via ElevenLabs (TTS)
  5. Publish translated audio back into the LiveKit room

Docs: https://docs.livekit.io/agents/
Run:
  python agent.py dev      # local dev with LiveKit Cloud
  python agent.py start    # production worker
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.plugins import openai as lk_openai
from livekit.plugins import elevenlabs, silero

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicebridge")

SOURCE_LANG     = os.getenv("SOURCE_LANGUAGE", "Korean")
TARGET_LANG     = os.getenv("TARGET_LANGUAGE", "English")
ARTIST_VOICE_ID = os.environ["ARTIST_VOICE_ID"]
EL_API_KEY      = os.environ["ELEVENLABS_API_KEY"]


# ─── Translation instructions ─────────────────────────────────────────────────

SYSTEM_PROMPT = (
    f"You are a real-time voice translator. "
    f"The user will speak in {SOURCE_LANG}. "
    f"Translate everything they say into natural, fluent {TARGET_LANG}. "
    f"Preserve the speaker's energy, emotion, and tone exactly. "
    f"Output ONLY the translated text — no explanations, no notes, no quotes."
)


# ─── Agent definition ─────────────────────────────────────────────────────────

class VoiceBridgeAgent(Agent):
    """
    A LiveKit 1.0 Agent that translates speech in real time.
    AgentSession wires VAD → STT → LLM → TTS automatically.
    """

    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self):
        # Greet on join — useful for testing the TTS voice is working
        await self.session.say("VoiceBridge connected. Ready to translate.", allow_interruptions=False)


# ─── Entrypoint ───────────────────────────────────────────────────────────────

async def entrypoint(ctx: JobContext):
    logger.info(f"Joining room: {ctx.room.name}")

    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # Wait for the artist / stream participant to join
    participant = await ctx.wait_for_participant()
    logger.info(f"Participant connected: {participant.identity}")

    # Build the ElevenLabs TTS with the cloned artist voice
    el_tts = elevenlabs.TTS(
        api_key=EL_API_KEY,
        voice_id=ARTIST_VOICE_ID,
        model="eleven_multilingual_v2",
        voice_settings=elevenlabs.VoiceSettings(
            stability=0.5,
            similarity_boost=0.85,
            style=0.2,
            use_speaker_boost=True,
        ),
    )

    # AgentSession is the v1.0 unified orchestrator
    # It owns the VAD → STT → LLM → TTS pipeline
    session = AgentSession(
        vad=silero.VAD.load(),
        stt=lk_openai.STT(
            model="whisper-1",
            language=SOURCE_LANG.lower()[:2],   # "ko" for Korean
        ),
        llm=lk_openai.LLM(model="gpt-4o"),
        tts=el_tts,
        # How long of silence = end of utterance (tune this for live streams)
        min_endpointing_delay=0.8,
        max_endpointing_delay=3.0,
    )

    await session.start(
        room=ctx.room,
        agent=VoiceBridgeAgent(),
        room_input_options=AgentSession.RoomInputOptions(
            # Only listen to the specific artist participant
            participant_identity=participant.identity,
        ),
    )

    logger.info("VoiceBridge session started — translating live")
    await asyncio.sleep(float("inf"))


# ─── Worker ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="voicebridge",
        )
    )
