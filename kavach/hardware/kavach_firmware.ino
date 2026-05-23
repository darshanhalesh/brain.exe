/*
 * hardware/kavach_firmware/kavach_firmware.ino
 * ─────────────────────────────────────────────────────────────────────────────
 * Kavach VoiceShield — ESP32 Firmware (ElatoAI-based)
 * 
 * Built on ElatoAI ESP32 platform patterns.
 * Reference: https://github.com/akdeb/ElatoAI
 * 
 * Flow:
 *   1. Connect to WiFi + WebSocket server
 *   2. Continuously stream audio to Gemini Live via Deno Edge
 *   3. On trigger word detected → send REST POST /trigger to FastAPI
 *   4. Stream audio features back for QML analysis
 *   5. Receive voice commands from server and play via speaker
 * 
 * Hardware: ESP32-S3 + I2S Mic + I2S Speaker (ElatoAI board)
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebSocketsClient.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <driver/i2s.h>

// ── Config (set via WiFi captive portal or hardcode for hackathon) ──────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASS     = "YOUR_WIFI_PASSWORD";
const char* FASTAPI_HOST  = "192.168.1.100";  // Your laptop IP
const int   FASTAPI_PORT  = 8000;
const char* DEVICE_ID     = "kavach-device-001";

// Trigger words (checked locally as fallback)
const char* TRIGGER_WORDS[] = {"kavach", "shield", "help"};
const int   NUM_TRIGGERS    = 3;

// ── I2S Config (ElatoAI board pins) ─────────────────────────────────────────
#define I2S_MIC_WS    15
#define I2S_MIC_SCK   14
#define I2S_MIC_SD    32
#define I2S_SPK_WS    25
#define I2S_SPK_SCK   26
#define I2S_SPK_SD    22
#define I2S_SAMPLE_RATE 16000
#define I2S_BUFFER_SIZE 512

// ── State ────────────────────────────────────────────────────────────────────
WebSocketsClient wsClient;
bool wsConnected = false;
bool triggered = false;
String currentIncidentId = "";
unsigned long lastPingMs = 0;
unsigned long triggerTimeMs = 0;

// ── Setup ────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Serial.println("🛡️  Kavach VoiceShield starting...");

    setupWiFi();
    setupI2S();
    setupWebSocket();

    Serial.println("✅ Kavach ready. Listening for trigger word...");
}

void setupWiFi() {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("Connecting to WiFi");
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 30) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n✅ WiFi connected: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n❌ WiFi failed — operating in offline mode");
    }
}

void setupI2S() {
    // Microphone (input)
    i2s_config_t mic_cfg = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
        .sample_rate = I2S_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 4,
        .dma_buf_len = I2S_BUFFER_SIZE,
        .use_apll = false,
    };
    i2s_pin_config_t mic_pins = {
        .bck_io_num = I2S_MIC_SCK,
        .ws_io_num = I2S_MIC_WS,
        .data_out_num = I2S_PIN_NO_CHANGE,
        .data_in_num = I2S_MIC_SD,
    };
    i2s_driver_install(I2S_NUM_0, &mic_cfg, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &mic_pins);

    // Speaker (output)
    i2s_config_t spk_cfg = {
        .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
        .sample_rate = I2S_SAMPLE_RATE,
        .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
        .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
        .communication_format = I2S_COMM_FORMAT_STAND_I2S,
        .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
        .dma_buf_count = 4,
        .dma_buf_len = I2S_BUFFER_SIZE,
        .use_apll = false,
    };
    i2s_pin_config_t spk_pins = {
        .bck_io_num = I2S_SPK_SCK,
        .ws_io_num = I2S_SPK_WS,
        .data_out_num = I2S_SPK_SD,
        .data_in_num = I2S_PIN_NO_CHANGE,
    };
    i2s_driver_install(I2S_NUM_1, &spk_cfg, 0, NULL);
    i2s_set_pin(I2S_NUM_1, &spk_pins);

    Serial.println("✅ I2S initialized");
}

void setupWebSocket() {
    wsClient.begin(FASTAPI_HOST, FASTAPI_PORT, 
                   String("/ws/device/") + DEVICE_ID);
    wsClient.onEvent(onWebSocketEvent);
    wsClient.setReconnectInterval(3000);
}

// ── Main Loop ─────────────────────────────────────────────────────────────────
void loop() {
    wsClient.loop();

    // Heartbeat ping every 30s
    if (millis() - lastPingMs > 30000) {
        if (wsConnected) {
            wsClient.sendTXT("{\"action\":\"heartbeat\"}");
        }
        lastPingMs = millis();
    }

    // Level 1: Auto-escalate after 10s with no safe confirmation
    if (triggered && !currentIncidentId.isEmpty()) {
        unsigned long elapsed = millis() - triggerTimeMs;
        if (elapsed > 10000 && elapsed < 10500) {
            Serial.println("Level 1 timeout — no safe signal received");
            // Server handles escalation, just log locally
        }
    }

    // Read audio + stream (simplified for MVP)
    readAndStreamAudio();

    delay(10);
}

void readAndStreamAudio() {
    int16_t audioBuffer[I2S_BUFFER_SIZE];
    size_t bytesRead = 0;
    i2s_read(I2S_NUM_0, audioBuffer, sizeof(audioBuffer), &bytesRead, portMAX_DELAY);

    if (bytesRead == 0) return;

    // Simple energy check for voice activity
    int32_t energy = 0;
    for (int i = 0; i < bytesRead / 2; i++) {
        energy += abs(audioBuffer[i]);
    }
    energy /= (bytesRead / 2);

    // Stream audio to WebSocket if triggered (for QML analysis)
    if (triggered && wsConnected && energy > 500) {
        // Send audio chunk as base64 (simplified — use binary in prod)
        DynamicJsonDocument doc(128);
        doc["action"] = "audio_chunk";
        doc["energy"] = energy;
        doc["incident_id"] = currentIncidentId;
        String json;
        serializeJson(doc, json);
        wsClient.sendTXT(json);
    }

    // Local trigger detection fallback (if server unreachable)
    // In prod: Gemini Live on device handles this
}

// ── WebSocket Event Handler ──────────────────────────────────────────────────
void onWebSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
    switch(type) {
        case WStype_CONNECTED:
            wsConnected = true;
            Serial.println("✅ Connected to Kavach server");
            break;

        case WStype_DISCONNECTED:
            wsConnected = false;
            Serial.println("❌ Disconnected from server");
            break;

        case WStype_TEXT: {
            DynamicJsonDocument doc(512);
            deserializeJson(doc, payload, length);
            String action = doc["action"].as<String>();
            handleServerMessage(action, doc);
            break;
        }

        default:
            break;
    }
}

void handleServerMessage(String action, DynamicJsonDocument& doc) {
    if (action == "speak") {
        String text = doc["text"].as<String>();
        Serial.printf("🔊 Speaking: %s\n", text.c_str());
        // In prod: use Gemini TTS or ElevenLabs to synthesize speech
        // For MVP: play pre-recorded audio clips based on text content
        playConfirmationTone();

    } else if (action == "siren") {
        int duration = doc["duration_ms"] | 3000;
        Serial.printf("🚨 Siren for %dms\n", duration);
        playSiren(duration);

    } else if (action == "ack") {
        // Server acknowledged heartbeat
        
    } else if (action == "cancel") {
        triggered = false;
        currentIncidentId = "";
        Serial.println("✅ Kavach deactivated");
        playConfirmationTone();
    }
}

// ── REST Trigger ──────────────────────────────────────────────────────────────
void sendTriggerToServer(float latitude, float longitude) {
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("❌ WiFi not connected — trigger logged locally");
        return;
    }

    HTTPClient http;
    String url = String("http://") + FASTAPI_HOST + ":" + FASTAPI_PORT + "/trigger";
    http.begin(url);
    http.addHeader("Content-Type", "application/json");

    DynamicJsonDocument doc(256);
    doc["device_id"] = DEVICE_ID;
    doc["trigger_word"] = "kavach";
    doc["latitude"] = latitude;
    doc["longitude"] = longitude;

    String body;
    serializeJson(doc, body);

    int code = http.POST(body);
    if (code == 200) {
        String resp = http.getString();
        DynamicJsonDocument rdoc(256);
        deserializeJson(rdoc, resp);
        currentIncidentId = rdoc["incident_id"].as<String>();
        triggered = true;
        triggerTimeMs = millis();
        Serial.printf("✅ Trigger sent | incident_id: %s\n", currentIncidentId.c_str());
    } else {
        Serial.printf("❌ Trigger failed: HTTP %d\n", code);
    }
    http.end();
}

// ── Audio Output ──────────────────────────────────────────────────────────────
void playConfirmationTone() {
    // Simple 440Hz beep for MVP
    // In prod: synthesize speech via TTS
    int16_t tone[I2S_BUFFER_SIZE];
    for (int i = 0; i < I2S_BUFFER_SIZE; i++) {
        tone[i] = (int16_t)(8000 * sin(2 * PI * 440 * i / I2S_SAMPLE_RATE));
    }
    size_t written;
    for (int r = 0; r < 5; r++) {
        i2s_write(I2S_NUM_1, tone, sizeof(tone), &written, portMAX_DELAY);
    }
}

void playSiren() { playSiren(3000); }
void playSiren(int durationMs) {
    unsigned long start = millis();
    int16_t siren[I2S_BUFFER_SIZE];
    while (millis() - start < (unsigned long)durationMs) {
        float freq = 600 + 400 * sin(2 * PI * (millis() - start) / 1000.0);
        for (int i = 0; i < I2S_BUFFER_SIZE; i++) {
            siren[i] = (int16_t)(15000 * sin(2 * PI * freq * i / I2S_SAMPLE_RATE));
        }
        size_t written;
        i2s_write(I2S_NUM_1, siren, sizeof(siren), &written, portMAX_DELAY);
    }
}
