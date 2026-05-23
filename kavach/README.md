# 🛡️ Kavach — VoiceShield

> Voice-triggered. Quantum-secured. Always ready.

A women's safety voice alert system combining ElatoAI ESP32 hardware, Quantum ML threat assessment, Post-Quantum Cryptography, and real-time emergency dispatch.

## Architecture

```
ESP32 (ElatoAI) → Gemini Live API → FastAPI Backend
                                         ├── QML Classifier (PennyLane VQC)
                                         ├── PQC Encryption (liboqs Kyber512)
                                         ├── Alert Optimizer (QUBO)
                                         ├── Twilio SMS / WhatsApp
                                         ├── 112 Emergency API
                                         └── Evidence Vault
                                         ↓
                                    Next.js Dashboard
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill env vars
cp .env.example .env

# 3. Train QML model
python quantum/train.py

# 4. Run backend
uvicorn backend.main:app --reload --port 8000

# 5. Run frontend (separate terminal)
cd frontend && npm install && npm run dev

# 6. Run tests
pytest tests/
```

## Project Structure

```
kavach/
├── hardware/          ESP32 Arduino firmware
├── quantum/           PennyLane VQC model
├── encryption/        liboqs Kyber512 wrapper
├── backend/           FastAPI orchestration server
├── frontend/          Next.js dashboard
└── tests/             End-to-end tests
```

## Threat Levels

| Level | Signal | Response |
|-------|--------|----------|
| 🟢 1 Low | Trigger + calm voice | Asks confirmation, starts recording |
| 🟡 2 Medium | Trigger + mild stress | Silent SOS, fake call, GPS every 30s |
| 🔴 3 High | Trigger + high panic | All contacts + 112 + siren |
| ⚫ 4 Critical | Silence post-threat | Auto-call 112, evidence upload |

## Quantum Components

- **QML**: PennyLane 4-qubit VQC on RAVDESS voice stress dataset
- **PQC**: liboqs Kyber512 (NIST-approved, quantum-resistant encryption)
- **Optimizer**: QUBO-based alert routing for contact priority
