// frontend/pages/index.js
// Kavach VoiceShield — Real-time Dashboard
// Run: npm install && npm run dev

import { useState, useEffect, useRef } from "react";
import Head from "next/head";

const THREAT_COLORS = {
  1: { bg: "#166534", text: "#4ade80", label: "🟢 Low" },
  2: { bg: "#854d0e", text: "#fbbf24", label: "🟡 Medium" },
  3: { bg: "#991b1b", text: "#f87171", label: "🔴 High" },
  4: { bg: "#1c1917", text: "#a8a29e", label: "⚫ Critical" },
};

export default function Dashboard() {
  const [incidents, setIncidents] = useState([]);
  const [activeIncident, setActiveIncident] = useState(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const ws = useRef(null);

  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const wsUrl = apiBase.replace("http", "ws") + "/ws/dashboard";

    const connect = () => {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        setConnected(true);
        addEvent("system", "Connected to Kavach server");
      };

      ws.current.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          handleEvent(msg);
        } catch {}
      };

      ws.current.onclose = () => {
        setConnected(false);
        addEvent("system", "Disconnected — reconnecting...");
        setTimeout(connect, 3000);
      };
    };

    connect();

    // Fetch initial incidents
    fetch(`${apiBase}/incidents?limit=10`)
      .then((r) => r.json())
      .then((d) => setIncidents(d.incidents || []))
      .catch(() => {});

    return () => ws.current?.close();
  }, []);

  const handleEvent = (msg) => {
    const { event } = msg;
    addEvent(event, JSON.stringify(msg).slice(0, 120));

    if (event === "trigger") {
      const inc = msg.incident;
      setIncidents((prev) => [inc, ...prev.filter((i) => i.id !== inc.id)]);
      setActiveIncident(inc);
    } else if (event === "threat_assessed") {
      setIncidents((prev) =>
        prev.map((i) =>
          i.id === msg.incident_id
            ? { ...i, threat_level: msg.threat_level, threat_score: msg.threat_score }
            : i
        )
      );
      setActiveIncident((prev) =>
        prev?.id === msg.incident_id
          ? { ...prev, threat_level: msg.threat_level, threat_score: msg.threat_score }
          : prev
      );
    } else if (event === "dispatched") {
      setIncidents((prev) =>
        prev.map((i) =>
          i.id === msg.incident_id ? { ...i, status: "dispatched" } : i
        )
      );
    } else if (event === "safe") {
      setIncidents((prev) =>
        prev.map((i) =>
          i.id === msg.incident_id ? { ...i, status: "resolved_safe" } : i
        )
      );
      if (activeIncident?.id === msg.incident_id) setActiveIncident(null);
    }
  };

  const addEvent = (type, text) => {
    setEvents((prev) => [
      { type, text, time: new Date().toLocaleTimeString() },
      ...prev.slice(0, 49),
    ]);
  };

  const markSafe = async (incidentId, deviceId) => {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/safe/${incidentId}?device_id=${deviceId}`,
      { method: "POST" }
    );
    if (res.ok) addEvent("action", `Marked ${incidentId} as safe`);
  };

  return (
    <>
      <Head>
        <title>Kavach VoiceShield — Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <div style={{ minHeight: "100vh", background: "#09090b", color: "#fafafa", fontFamily: "system-ui, sans-serif" }}>
        
        {/* Header */}
        <header style={{ borderBottom: "1px solid #27272a", padding: "12px 24px", display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 22, fontWeight: 700 }}>🛡️ Kavach</span>
          <span style={{ color: "#71717a", fontSize: 14 }}>VoiceShield Dashboard</span>
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: connected ? "#22c55e" : "#ef4444" }} />
            <span style={{ fontSize: 13, color: "#71717a" }}>{connected ? "Live" : "Offline"}</span>
          </div>
        </header>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 0, height: "calc(100vh - 56px)" }}>
          
          {/* Main */}
          <div style={{ padding: 24, overflowY: "auto" }}>
            
            {/* Active Incident Banner */}
            {activeIncident && (
              <div style={{
                background: THREAT_COLORS[activeIncident.threat_level]?.bg || "#1c1917",
                border: `1px solid ${THREAT_COLORS[activeIncident.threat_level]?.text || "#f87171"}`,
                borderRadius: 12, padding: 20, marginBottom: 24,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: THREAT_COLORS[activeIncident.threat_level]?.text }}>
                      {THREAT_COLORS[activeIncident.threat_level]?.label} — ACTIVE INCIDENT
                    </div>
                    <div style={{ fontSize: 13, color: "#a1a1aa", marginTop: 4 }}>
                      ID: {activeIncident.id} | Device: {activeIncident.device_id}
                    </div>
                    <div style={{ fontSize: 13, color: "#a1a1aa" }}>
                      📍 {activeIncident.latitude?.toFixed(4)}, {activeIncident.longitude?.toFixed(4)}
                    </div>
                    {activeIncident.threat_score > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <div style={{ fontSize: 12, color: "#a1a1aa", marginBottom: 4 }}>QML Threat Score</div>
                        <div style={{ background: "#27272a", borderRadius: 99, height: 8, width: 200 }}>
                          <div style={{
                            background: THREAT_COLORS[activeIncident.threat_level]?.text,
                            borderRadius: 99, height: "100%",
                            width: `${(activeIncident.threat_score * 100).toFixed(0)}%`,
                            transition: "width 0.5s ease",
                          }} />
                        </div>
                        <div style={{ fontSize: 12, color: "#a1a1aa", marginTop: 2 }}>
                          {(activeIncident.threat_score * 100).toFixed(1)}% stress probability
                        </div>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => markSafe(activeIncident.id, activeIncident.device_id)}
                    style={{
                      background: "#166534", color: "#4ade80", border: "1px solid #4ade80",
                      borderRadius: 8, padding: "8px 16px", cursor: "pointer", fontWeight: 600, fontSize: 13,
                    }}
                  >
                    ✅ Mark Safe
                  </button>
                </div>
                <div style={{ marginTop: 12 }}>
                  <a
                    href={`https://maps.google.com/?q=${activeIncident.latitude},${activeIncident.longitude}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#60a5fa", fontSize: 13 }}
                  >
                    🗺️ Open in Google Maps →
                  </a>
                </div>
              </div>
            )}

            {/* Incidents Table */}
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: "#e4e4e7" }}>
                Incidents
              </h2>
              {incidents.length === 0 ? (
                <div style={{ color: "#52525b", padding: "32px 0", textAlign: "center", fontSize: 14 }}>
                  No incidents yet. Device is monitoring.
                </div>
              ) : (
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid #27272a", color: "#71717a", textAlign: "left" }}>
                      {["ID", "Level", "Score", "Status", "Location", "Time", ""].map((h) => (
                        <th key={h} style={{ padding: "8px 12px", fontWeight: 500 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {incidents.map((inc) => {
                      const colors = THREAT_COLORS[inc.threat_level] || THREAT_COLORS[1];
                      return (
                        <tr
                          key={inc.id}
                          onClick={() => setActiveIncident(inc)}
                          style={{
                            borderBottom: "1px solid #18181b", cursor: "pointer",
                            background: activeIncident?.id === inc.id ? "#18181b" : "transparent",
                          }}
                        >
                          <td style={{ padding: "10px 12px", fontFamily: "monospace", color: "#a1a1aa" }}>{inc.id}</td>
                          <td style={{ padding: "10px 12px" }}>
                            <span style={{
                              background: colors.bg, color: colors.text,
                              padding: "2px 8px", borderRadius: 99, fontSize: 12, fontWeight: 600,
                            }}>
                              {colors.label}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", color: colors.text }}>
                            {inc.threat_score ? `${(inc.threat_score * 100).toFixed(0)}%` : "—"}
                          </td>
                          <td style={{ padding: "10px 12px", color: "#a1a1aa" }}>{inc.status}</td>
                          <td style={{ padding: "10px 12px", color: "#71717a", fontSize: 12 }}>
                            {inc.latitude?.toFixed(3)}, {inc.longitude?.toFixed(3)}
                          </td>
                          <td style={{ padding: "10px 12px", color: "#52525b", fontSize: 12 }}>
                            {new Date(inc.created_at).toLocaleTimeString()}
                          </td>
                          <td style={{ padding: "10px 12px" }}>
                            {inc.status !== "resolved_safe" && (
                              <button
                                onClick={(e) => { e.stopPropagation(); markSafe(inc.id, inc.device_id); }}
                                style={{
                                  background: "transparent", color: "#4ade80", border: "1px solid #166534",
                                  borderRadius: 6, padding: "3px 10px", cursor: "pointer", fontSize: 12,
                                }}
                              >
                                Safe
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Sidebar — Event Log */}
          <div style={{ borderLeft: "1px solid #27272a", padding: 16, overflowY: "auto" }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: "#71717a", marginBottom: 12, textTransform: "uppercase", letterSpacing: 1 }}>
              Live Events
            </h3>
            {events.map((ev, i) => (
              <div key={i} style={{ marginBottom: 10, paddingBottom: 10, borderBottom: "1px solid #18181b" }}>
                <div style={{ fontSize: 11, color: "#52525b", marginBottom: 2 }}>
                  {ev.time} · <span style={{ color: "#71717a" }}>{ev.type}</span>
                </div>
                <div style={{ fontSize: 12, color: "#a1a1aa", wordBreak: "break-all" }}>{ev.text}</div>
              </div>
            ))}
            {events.length === 0 && (
              <div style={{ color: "#3f3f46", fontSize: 13 }}>Waiting for events...</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
