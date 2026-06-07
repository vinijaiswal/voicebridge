"""
VoiceBridge Token Server
-------------------------
FastAPI server that issues LiveKit JWT tokens.

Endpoints:
  GET /token/artist?room=xxx&identity=artist-1
    → publisher token (can publish audio)

  GET /token/fan?room=xxx&identity=fan-abc
    → subscriber token (can subscribe to tracks, cannot publish)

  GET /health
    → { "status": "ok" }

Run:
  uvicorn token_server:app --port 8080 --reload
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv

load_dotenv()

LIVEKIT_API_KEY    = os.environ["LIVEKIT_API_KEY"]
LIVEKIT_API_SECRET = os.environ["LIVEKIT_API_SECRET"]

app = FastAPI(title="VoiceBridge Token Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock this down in production
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _make_token(
    room: str,
    identity: str,
    can_publish: bool,
    can_subscribe: bool,
    ttl_seconds: int = 7200,
) -> str:
    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room,
                can_publish=can_publish,
                can_subscribe=can_subscribe,
                can_publish_data=False,
            )
        )
        .with_ttl(ttl_seconds)
        .to_jwt()
    )
    return token


@app.get("/token/artist")
def artist_token(
    room: str = Query(..., description="Room name, e.g. 'concert-live'"),
    identity: str = Query("artist", description="Participant identity"),
):
    """
    Issues a publisher token for the artist.
    Use this from the ingest script that captures the YouTube/stream audio.
    """
    try:
        token = _make_token(room, identity, can_publish=True, can_subscribe=False)
        return {"token": token, "room": room, "identity": identity, "role": "artist"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/token/fan")
def fan_token(
    room: str = Query(..., description="Room name"),
    identity: str = Query(..., description="Unique fan identity, e.g. 'fan-user123'"),
):
    """
    Issues a subscriber-only token for a fan.
    Call this from your frontend when a fan wants to join.
    """
    try:
        token = _make_token(room, identity, can_publish=False, can_subscribe=True)
        return {"token": token, "room": room, "identity": identity, "role": "fan"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}
