"""
VoiceBridge Token Server
-------------------------
One-file FastAPI server.

GET /token?room=xxx&identity=yyy&role=artist|fan
  → { token, livekit_url, room, identity }

GET /health
  → { status: "ok" }
"""

import os
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

LK_KEY    = os.environ["LIVEKIT_API_KEY"]
LK_SECRET = os.environ["LIVEKIT_API_SECRET"]
LK_URL    = os.environ["LIVEKIT_URL"]


@app.get("/token")
def get_token(
    room: str     = Query(...),
    identity: str = Query(...),
    role: str     = Query("fan"),   # "artist" or "fan"
):
    can_publish   = role == "artist"
    can_subscribe = True

    token = (
        AccessToken(LK_KEY, LK_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(VideoGrants(
            room_join=True,
            room=room,
            can_publish=can_publish,
            can_subscribe=can_subscribe,
        ))
        .to_jwt()
    )
    return {"token": token, "livekit_url": LK_URL, "room": room, "identity": identity}


@app.get("/health")
def health():
    return {"status": "ok"}
