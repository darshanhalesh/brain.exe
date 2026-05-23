#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Kavach VoiceShield — Quick Start (Hackathon Mode)
# Run this script to get everything running in minutes.
# ─────────────────────────────────────────────────────────────────────────────

set -e
echo "🛡️  Starting Kavach VoiceShield..."

# 1. Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install fastapi uvicorn[standard] pennylane numpy scikit-learn \
    librosa python-dotenv httpx pydantic pydantic-settings \
    twilio boto3 aiofiles python-multipart loguru cryptography \
    pytest pytest-asyncio --quiet

# 2. Copy .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env
    echo "⚠️  Created .env — add your API keys before demo!"
fi

# 3. Train QML model (synthetic data fallback)
echo "🧠 Training QML model (synthetic data)..."
python quantum/train.py

# 4. Run tests
echo "🧪 Running tests..."
pytest tests/ -v --tb=short 2>/dev/null || echo "⚠️  Some tests failed — check output above"

# 5. Start backend
echo "🚀 Starting FastAPI backend on :8000..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

sleep 2

# 6. Health check
echo "🔍 Health check..."
curl -s http://localhost:8000/health | python -m json.tool || echo "Backend not responding yet"

echo ""
echo "✅ Kavach is running!"
echo ""
echo "  API:       http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Dashboard: cd frontend && npm install && npm run dev"
echo ""
echo "🧪 Test trigger:"
echo "  curl -X POST http://localhost:8000/trigger \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"device_id\":\"kavach-001\",\"trigger_word\":\"kavach\",\"latitude\":12.9716,\"longitude\":77.5946}'"
echo ""
echo "Press Ctrl+C to stop"
wait $BACKEND_PID
