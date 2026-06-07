"""
VoiceBridge Agent — LiveKit Agents 1.0
Clean version — no RoomInputOptions
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

SYSTEM_PROMPT = (
    f"You are a real-time voice translator. "
    f"The user will speak in {SOURCE_LANG}. "
    f"Translate everything they say into natural, fluent {TARGET_LANG}. "
    f"Preserve the speaker's energy, emotion, and tone exactly. "
    f"Output ONLY the translated text — no explanations, no notes, no quotes."
)


class VoiceBridgeAgent(Agent):
    def __init__(self):
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self):
        logger.info("✅ Agent entered room — pipeline active")
        await self.session.say("VoiceBridge connected.", allow_interruptions=False)
        logger.info("✅ TTS working")


async def entrypoint(ctx: JobContext):
    logger.info(f"🔌 Job received — room: {ctx.room.name}")
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("✅ Connected to room")

    participant = await ctx.wait_for_participant()
    logger.info(f"✅ Participant: {participant.identity}")

    session = AgentSession(
        vad=silero.VAD.load(),
        stt=lk_openai.STT(model="whisper-1", language="ko"),
        llm=lk_openai.LLM(model="gpt-4o"),
        tts=elevenlabs.TTS(
            api_key=EL_API_KEY,
            voice_id=ARTIST_VOICE_ID,
            model="eleven_multilingual_v2",
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.5,
                similarity_boost=0.85,
                style=0.2,
                use_speaker_boost=True,
            ),
        ),
        min_endpointing_delay=0.8,
        max_endpointing_delay=3.0,
    )

    @session.on("user_speech_committed")
    def on_speech(msg):
        logger.info(f"🎤 Heard: '{msg.content}'")

    @session.on("agent_speech_committed")
    def on_agent(msg):
        logger.info(f"🔊 Speaking: '{msg.content}'")

    await session.start(room=ctx.room, agent=VoiceBridgeAgent())
    logger.info("🚀 Listening for Korean speech...")
    await asyncio.sleep(float("inf"))


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="voicebridge"))
