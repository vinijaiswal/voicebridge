#!/bin/bash
# Run from inside the agent/ folder:
#   cd agent && ./start.sh

set -e

if [ ! -f .env ]; then
  echo "❌  No .env found. Make sure you're inside the agent/ folder."
  exit 1
fi

# Virtualenv
if [ ! -d .venv ]; then
  echo "📦  Creating virtualenv..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# Dependencies
echo "📦  Checking dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# ffmpeg
if ! command -v ffmpeg &>/dev/null; then
  echo "📦  Installing ffmpeg..."
  if command -v brew &>/dev/null; then
    brew install ffmpeg
  else
    echo "❌  ffmpeg not found. Run: sudo apt install ffmpeg"
    exit 1
  fi
fi

echo ""
echo "🌐  VoiceBridge starting (LiveKit Agents 1.0)..."
echo ""

# Token server — run in background, wait up to 8s for it to be ready
echo "▶   Token server → http://localhost:8080"
uvicorn server:app --port 8080 --log-level warning &
TOKEN_PID=$!

echo -n "    Waiting for token server"
for i in 1 2 3 4 5 6 7 8; do
  sleep 1
  echo -n "."
  if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
    echo " ✓"
    break
  fi
  if [ $i -eq 8 ]; then
    echo ""
    echo "❌  Token server didn't respond. Run ./debug_server.sh to see the error."
    kill $TOKEN_PID 2>/dev/null
    exit 1
  fi
done

# Translation agent
echo "▶   Translation agent"
python agent.py dev &
AGENT_PID=$!

echo ""
echo "✅  Running!"
echo ""
echo "   ── Next step: open a NEW terminal tab and run ──"
echo ""
echo "   cd $(pwd)"
echo "   source .venv/bin/activate"
echo "   python ingest.py --url ./JK_v1.m4a --room concert-live"
echo ""
echo "   Then open: $(pwd)/../frontend/index.html"
echo "   Room: concert-live"
echo ""
echo "   Ctrl+C to stop all processes"
echo ""

trap "echo ''; echo 'Stopping…'; kill $TOKEN_PID $AGENT_PID 2>/dev/null; exit 0" SIGINT SIGTERM
wait
