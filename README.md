🛡️ Kavach — VoiceShield
Voice-triggered. Quantum-secured. Always ready.

A women's safety voice alert system that combines an ESP32 hardware device, Google Gemini Live API for voice recognition, Quantum Machine Learning for threat assessment, Post-Quantum Cryptography for secure dispatch, and real-time emergency coordination across SMS, WhatsApp, and India's 112 emergency services.

Table of Contents
Overview
Architecture
Features
Threat Levels
Tech Stack
Project Structure
Setup & Installation
Environment Variables
API Reference
Quantum Components
Hardware
Running Tests
Roadmap
Overview
Kavach (Sanskrit: armour) is an IoT safety device and cloud system designed for personal security. A user wears or carries an ESP32-based device. When a trigger word is spoken ("kavach", "shield", "bachao", "help me"), the system:

Detects the trigger via Gemini Live API
Records audio and extracts voice stress features (pitch, speech rate, pauses)
Runs a Quantum ML classifier to determine threat severity
Encrypts the SOS payload with NIST-approved post-quantum cryptography (Kyber512)
Dispatches alerts across all appropriate channels — SMS, WhatsApp, 112 police API, and an encrypted evidence vault
Streams real-time status to a Next.js monitoring dashboard
The system auto-escalates if no "safe" confirmation is received within 10 seconds of activation.

Architecture
ESP32 (ElatoAI)
    │  I2S audio stream
    ▼
Gemini Live API  ──── trigger word + initial stress estimate
    │
    ▼
FastAPI Backend (Python)
    ├── QML Classifier (PennyLane 4-qubit VQC)   ← quantum threat scoring
    ├── PQC Encryption (liboqs Kyber512)           ← quantum-safe encryption
    ├── Alert Optimizer (QUBO contact ranking)     ← quantum-inspired routing
    ├── Twilio  → SMS + WhatsApp
    ├── 112 Emergency API  → police dispatch
    └── AWS S3  → encrypted evidence vault
              │
              ▼ WebSocket
         Next.js Dashboard  (real-time incident monitor)
Features
Wake-word activation — responds to "kavach", "shield", "bachao", "help me" in multiple languages
Quantum threat scoring — 4-qubit Variational Quantum Circuit classifies voice stress from pitch, speech rate, and pause patterns
Auto-escalation — if no "safe" confirmation within 10 seconds, automatically escalates to Level 2 and contacts are notified
MONITOR mode — passive location tracking; escalates to Level 2 if the device goes silent for 10 minutes
Post-quantum encryption — every SOS payload is encrypted with Kyber512 + AES-256-GCM before transmission
QUBO-optimised contact routing — determines the best alert order based on proximity, response history, and priority weight
Multilingual support — Gemini detects language (English, Hindi, Kannada, Telugu, etc.)
Fake call — device can receive a "fake incoming call" via WebSocket command to deter an aggressor
Siren mode — ESP32 speaker triggers a loud alarm on Level 3+ events
Encrypted evidence vault — incident payloads uploaded to AWS S3 with KMS server-side encryption
Real-time dashboard — Next.js frontend connected via WebSocket shows live incident state, threat scores, and alert logs
Threat Levels
Level	Trigger Condition	Automated Response
🟢 1 — Low	Trigger word detected, calm voice	Confirms activation, starts audio recording, waits for "safe"
🟡 2 — Medium	Mild stress detected or no "safe" in 10s	Silent SOS to closest contact, fake call, GPS update every 30s
🔴 3 — High	High panic score from QML	All contacts + 112 emergency API + device siren + WhatsApp
⚫ 4 — Critical	Post-threat silence / critical QML score	Auto-call 112, evidence upload, all channels simultaneously
Tech Stack
Layer	Technology
Hardware	ESP32-S3 (ElatoAI board), I2S microphone + speaker
Voice AI	Google Gemini Live API (gemini-2.0-flash-exp)
Backend	Python 3.11, FastAPI, Uvicorn, WebSockets
Quantum ML	PennyLane 0.36, default.qubit device, VQC with StronglyEntanglingLayers
Audio features	librosa (pitch, ZCR, RMS, MFCC)
Post-quantum crypto	liboqs Kyber512 + AES-256-GCM (HKDF key derivation)
Alert dispatch	Twilio REST API (SMS + WhatsApp)
Emergency	India 112 API (configurable endpoint)
Evidence vault	AWS S3 + KMS server-side encryption
Frontend	Next.js, WebSocket, vanilla CSS
Testing	pytest, pytest-asyncio
Project Structure
kavach/
├── hardware/
│   └── kavach_firmware.ino     # ESP32 Arduino firmware (ElatoAI platform)
│
├── quantum/
│   ├── classifier.py           # VQC inference — threat scoring from voice features
│   ├── features.py             # librosa audio feature extraction
│   ├── train.py                # Train VQC on RAVDESS voice stress dataset
│   └── model/                  # Auto-created by train.py
│       ├── vqc_weights.npy
│       ├── scaler.pkl
│       └── meta.json
│
├── encryption/
│   └── pqc.py                  # Kyber512 + AES-256-GCM wrapper (liboqs)
│
├── backend/
│   ├── main.py                 # FastAPI app — all routes and WebSocket handlers
│   ├── alerts.py               # Twilio SMS/WhatsApp + 112 API + evidence vault
│   ├── gemini.py               # Gemini Live API trigger detection
│   ├── optimizer.py            # QUBO-inspired contact priority ranking
│   ├── websocket_manager.py    # Dashboard + device WebSocket connection pool
│   └── state.py                # In-memory incident store and device registry
│
├── frontend/
│   ├── pages/index.js          # Real-time Next.js monitoring dashboard
│   └── package.json
│
├── tests/
│   └── test_e2e.py             # End-to-end pytest suite
│
├── requirements.txt
├── .env.example
└── start.sh
Setup & Installation
Prerequisites
Python 3.11+
Node.js 18+
An ElatoAI ESP32-S3 board (or any ESP32-S3 with I2S mic + speaker)
Arduino IDE with ESP32 board support
1. Clone and install Python dependencies
git clone https://github.com/your-org/kavach-voiceshield.git
cd kavach-voiceshield
pip install -r requirements.txt
2. Install post-quantum crypto (optional but recommended)
# Kyber512 via liboqs-python
pip install liboqs-python
# Without this, the system falls back to AES-256-GCM demo mode
3. Configure environment
cp .env.example .env
# Fill in your API keys (see Environment Variables below)
4. Train the QML model
python quantum/train.py
# Downloads RAVDESS dataset, trains 4-qubit VQC, saves weights to quantum/model/
Skip training for a quick demo — the backend falls back to a heuristic stress scorer if quantum/model/vqc_weights.npy is not found.

5. Start the backend
uvicorn backend.main:app --reload --port 8000
6. Start the frontend
cd frontend
npm install
npm run dev
# Dashboard available at http://localhost:3000
7. Run all at once
chmod +x start.sh && ./start.sh
8. Flash the ESP32
Open hardware/kavach_firmware.ino in the Arduino IDE, update WIFI_SSID, WIFI_PASS, and FASTAPI_HOST with your local machine's IP address, then flash to your ESP32-S3 board.

Environment Variables
Copy .env.example to .env and populate these values:

Variable	Description
GEMINI_API_KEY	Google Gemini API key
TWILIO_ACCOUNT_SID	Twilio account SID
TWILIO_AUTH_TOKEN	Twilio auth token
TWILIO_FROM_NUMBER	Twilio sender number (E.164 format)
TRUSTED_CONTACTS	Comma-separated phone numbers for SOS recipients
EMERGENCY_API_URL	112 emergency endpoint (mock by default)
EMERGENCY_API_KEY	API key for emergency services
AWS_ACCESS_KEY_ID	AWS credentials for evidence vault
AWS_SECRET_ACCESS_KEY	AWS secret key
AWS_BUCKET_NAME	S3 bucket for encrypted evidence
AWS_REGION	AWS region (default: ap-south-1)
QML_THREAT_THRESHOLD_LOW	Score threshold for Level 2 (default: 0.3)
QML_THREAT_THRESHOLD_MEDIUM	Score threshold for Level 3 (default: 0.6)
QML_THREAT_THRESHOLD_HIGH	Score threshold for Level 4 (default: 0.85)
API Reference
Method	Endpoint	Description
GET	/health	System health — QML status, PQC scheme
POST	/trigger	ESP32 reports trigger word detection; creates incident
POST	/assess	Run QML threat scoring from voice feature floats
POST	/assess/audio	Run QML threat scoring from raw audio file upload
POST	/dispatch	Encrypt and dispatch SOS across all channels
POST	/safe/{incident_id}	User confirms safety; cancels escalation
GET	/status/{incident_id}	Get full incident record
GET	/incidents	List recent incidents (latest 20)
POST	/monitor/start	Start passive MONITOR mode (5-min location pings)
POST	/monitor/stop	Stop MONITOR mode
WS	/ws/dashboard	Real-time event stream for the Next.js dashboard
WS	/ws/device/{id}	Bidirectional channel for ESP32 commands (speak, siren, ack)
Interactive API docs available at http://localhost:8000/docs when the backend is running.

Quantum Components
Kavach uses three quantum or quantum-inspired components:

1. Quantum ML Classifier (quantum/classifier.py)
A 4-qubit Variational Quantum Circuit built with PennyLane:

Encoding — AngleEmbedding maps normalised voice features (pitch, pitch variance, speech rate, pause ratio) onto qubit rotation angles
Ansatz — StronglyEntanglingLayers with 2 layers of parameterised rotations and entangling gates
Measurement — PauliZ expectation on qubit 0 converted to a threat probability in [0, 1]
Training data — RAVDESS voice emotion dataset, labelled for stress levels
Fallback — if model weights are absent, a hand-tuned heuristic scorer runs instead
Threat score → Level mapping:
  0.00 – 0.30  →  Level 1 (Low)
  0.30 – 0.60  →  Level 2 (Medium)
  0.60 – 0.85  →  Level 3 (High)
  0.85 – 1.00  →  Level 4 (Critical)
2. Post-Quantum Encryption (encryption/pqc.py)
A hybrid encryption scheme using NIST-standardised Kyber512:

Kyber512 KEM  →  shared secret
                      │
                   HKDF-SHA256  →  AES-256 key
                                          │
                                   AES-256-GCM  →  encrypted SOS payload
Each incident generates a fresh Kyber keypair, providing forward secrecy. When liboqs-python is not installed, the system falls back to direct AES-256-GCM with a random 32-byte key (clearly labelled AES256GCM_demo in responses).

3. QUBO Alert Optimizer (backend/optimizer.py)
A quantum-inspired greedy optimizer that ranks trusted contacts for sequential or parallel alerting:

score(contact) = 0.4 × (1 / distance_km)
               + 0.4 × (1 / avg_response_time_s)
               + 0.2 × (priority_weight / 5)
At Level 3–4, all contacts are alerted simultaneously. At Level 1–2, contacts are alerted in ranked order to avoid alert fatigue.

Hardware
The firmware targets the ElatoAI ESP32-S3 board (ElatoAI GitHub) and can be adapted to any ESP32-S3 with an I2S microphone and I2S speaker.

Default pin mapping:

Signal	GPIO
Mic WS (word select)	15
Mic SCK (clock)	14
Mic SD (data)	32
Speaker WS	25
Speaker SCK	26
Speaker SD	22
Firmware flow:

Connect to WiFi and open a WebSocket to the FastAPI backend
Stream I2S audio to Gemini Live API via Deno Edge for trigger detection
On trigger detection, POST /trigger to FastAPI to create an incident
Receive spoken feedback from server (e.g., "Kavach activated. Say 'safe' to cancel.")
On Level 3+, receive siren WebSocket command and play alarm audio
Send heartbeat pings every 30 seconds; server watches for silence in MONITOR mode
Running Tests
pytest tests/ -v
The end-to-end test suite (tests/test_e2e.py) covers:

Full trigger → assess → dispatch pipeline
Auto-escalation timer logic
PQC encrypt/decrypt round-trip
QML classifier heuristic fallback
WebSocket dashboard event delivery
MONITOR mode start/stop
Evidence vault upload simulation
Roadmap
 Real Kyber512 key exchange between ESP32 and server (currently server-side only)
 Replace simulated contact distances with Google Maps Distance Matrix API
 MONITOR mode live GPS updates streamed from ESP32
 Direct 112 India production API integration
 Train QML model on larger, more diverse voice stress corpus
 OTA firmware updates for the ESP32
 Mobile companion app (React Native) with trusted-contact management
 Multi-device support for family safety networks
License
MIT License — see LICENSE for details.

Acknowledgements
ElatoAI for the ESP32 voice AI platform patterns
PennyLane for the quantum ML framework
Open Quantum Safe / liboqs for the Kyber512 implementation
NIST Post-Quantum Cryptography Standardisation for the Kyber512 standard
RAVDESS for the voice emotion dataset used in QML training
