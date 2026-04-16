import { useState, useEffect, useRef } from "react";

const MOCK_DIFF = {
  source: "gate_alpha.nous",
  target: "gate_alpha_v2.nous",
  verdict: { critical: 1, warning: 4, info: 4 },
  topology: {
    added: [],
    removed: ["Monitor"],
    modified: ["Scout"],
    route_changes: [
      { from: "Scanner→Monitor", to: null, type: "removed" },
    ],
  },
  cost: {
    souls: [
      { name: "Scout", before: 0.0045, after: 0.00035, tier_before: "Tier1", tier_after: "Groq" },
      { name: "Hunter", before: 0.0045, after: 0.0045, tier_before: "Tier1", tier_after: "Tier1" },
      { name: "Quant", before: 0.000375, after: 0.000375, tier_before: "Tier2", tier_after: "Tier2" },
      { name: "Monitor", before: 0.0075, after: null, tier_before: "Tier2", tier_after: null },
    ],
    total_before: 0.016875,
    total_after: 0.005225,
    daily_before: 4.86,
    daily_after: 1.50,
    monthly_before: 145.80,
    monthly_after: 45.14,
  },
  protocol: {
    messages_added: [],
    messages_removed: ["MonitorAlert"],
    mismatches: [],
  },
  performance: {
    heartbeat_changes: [],
    wake_strategy_changes: [
      { soul: "Scout", from: "LISTENER", to: "HEARTBEAT" },
    ],
  },
  capabilities: {
    senses_added: [{ soul: "Scout", sense: "mcp_call" }],
    senses_removed: [{ soul: "Monitor", sense: "http_get" }],
  },
  memory: {
    fields_added: [{ soul: "Scout", field: "last_mcp_call", type: "timestamp" }],
    fields_removed: [{ soul: "Monitor", field: "alert_count", type: "int" }],
  },
  findings: [
    { severity: "CRITICAL", code: "BD-C001", category: "Cost", message: "Total cost change: -69.0%" },
    { severity: "WARNING", code: "BD-W001", category: "Topology", message: "Soul removed: Monitor" },
    { severity: "WARNING", code: "BD-W002", category: "Cost", message: "Soul Scout: tier changed Tier1 → Groq" },
    { severity: "WARNING", code: "BD-W003", category: "Protocol", message: "Message type removed: MonitorAlert" },
    { severity: "WARNING", code: "BD-W004", category: "Capability", message: "Soul Monitor: sense removed http_get" },
    { severity: "INFO", code: "BD-I001", category: "Topology", message: "Soul modified: Scout" },
    { severity: "INFO", code: "BD-I002", category: "Performance", message: "Scout: wake strategy LISTENER → HEARTBEAT" },
    { severity: "INFO", code: "BD-I003", category: "Capability", message: "Scout: sense added mcp_call" },
    { severity: "INFO", code: "BD-I004", category: "Memory", message: "Scout: field added last_mcp_call (timestamp)" },
  ],
};

const GOLD = "#c9a554";
const GOLD_DIM = "rgba(201,165,84,0.15)";
const GOLD_BORDER = "rgba(201,165,84,0.25)";
const BG_CARD = "rgba(10,14,28,0.85)";
const BG_DEEP = "#05070e";
const RED = "#e05252";
const RED_DIM = "rgba(224,82,82,0.12)";
const GREEN = "#4ade80";
const GREEN_DIM = "rgba(74,222,128,0.12)";
const AMBER = "#f59e0b";
const AMBER_DIM = "rgba(245,158,11,0.12)";
const BLUE = "#60a5fa";
const BLUE_DIM = "rgba(96,165,250,0.12)";
const PURPLE = "#a78bfa";
const CYAN = "#22d3ee";
const TEXT = "#e2e8f0";
const TEXT_DIM = "#94a3b8";

function AnimatedNumber({ value, prefix = "", suffix = "", decimals = 2, duration = 1200 }) {
  const [display, setDisplay] = useState(0);
  const ref = useRef(null);
  useEffect(() => {
    let start = null;
    const from = 0;
    const to = value;
    function step(ts) {
      if (!start) start = ts;
      const p = Math.min((ts - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay(from + (to - from) * eased);
      if (p < 1) ref.current = requestAnimationFrame(step);
    }
    ref.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(ref.current);
  }, [value, duration]);
  return <span>{prefix}{display.toFixed(decimals)}{suffix}</span>;
}

function SeverityBadge({ severity }) {
  const map = {
    CRITICAL: { bg: RED_DIM, border: RED, color: RED, icon: "✗" },
    WARNING: { bg: AMBER_DIM, border: AMBER, color: AMBER, icon: "⚠" },
    INFO: { bg: BLUE_DIM, border: BLUE, color: BLUE, icon: "ℹ" },
  };
  const s = map[severity] || map.INFO;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "2px 10px", borderRadius: 4,
      background: s.bg, border: `1px solid ${s.border}`,
      color: s.color, fontSize: 11, fontWeight: 600,
      fontFamily: "'JetBrains Mono', monospace", letterSpacing: "0.04em",
    }}>
      {s.icon} {severity}
    </span>
  );
}

function VerdictBanner({ verdict, source, target }) {
  const total = verdict.critical + verdict.warning + verdict.info;
  const breaking = verdict.critical > 0;
  return (
    <div style={{
      background: breaking
        ? "linear-gradient(135deg, rgba(224,82,82,0.08) 0%, rgba(10,14,28,0.95) 60%)"
        : "linear-gradient(135deg, rgba(74,222,128,0.08) 0%, rgba(10,14,28,0.95) 60%)",
      border: `1px solid ${breaking ? "rgba(224,82,82,0.3)" : "rgba(74,222,128,0.3)"}`,
      borderRadius: 12, padding: "20px 24px",
      display: "flex", alignItems: "center", justifyContent: "space-between",
      flexWrap: "wrap", gap: 16,
    }}>
      <div>
        <div style={{
          fontFamily: "'Playfair Display', serif", fontSize: 20, fontWeight: 700,
          color: breaking ? RED : GREEN, marginBottom: 6,
        }}>
          {breaking ? "BREAKING CHANGES DETECTED" : "SAFE TO DEPLOY"}
        </div>
        <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: TEXT_DIM }}>
          {source} → {target} · {total} finding{total !== 1 ? "s" : ""}
        </div>
      </div>
      <div style={{ display: "flex", gap: 12 }}>
        {verdict.critical > 0 && (
          <CountPill count={verdict.critical} label="Critical" color={RED} bg={RED_DIM} />
        )}
        {verdict.warning > 0 && (
          <CountPill count={verdict.warning} label="Warning" color={AMBER} bg={AMBER_DIM} />
        )}
        {verdict.info > 0 && (
          <CountPill count={verdict.info} label="Info" color={BLUE} bg={BLUE_DIM} />
        )}
      </div>
    </div>
  );
}

function CountPill({ count, label, color, bg }) {
  return (
    <div style={{
      background: bg, border: `1px solid ${color}33`,
      borderRadius: 8, padding: "8px 16px", textAlign: "center", minWidth: 72,
    }}>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>
        {count}
      </div>
      <div style={{ fontSize: 10, color, opacity: 0.8, textTransform: "uppercase", letterSpacing: "0.08em" }}>
        {label}
      </div>
    </div>
  );
}

function CostImpactCard({ cost }) {
  const pctChange = ((cost.total_after - cost.total_before) / cost.total_before * 100);
  const isDown = pctChange < 0;
  const monthSaved = cost.monthly_before - cost.monthly_after;
  return (
    <div style={{
      background: BG_CARD, border: `1px solid ${GOLD_BORDER}`, borderRadius: 12,
      padding: 24, flex: "1 1 340px", minWidth: 300,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <span style={{ fontSize: 18 }}>◎</span>
        <span style={{
          fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 600, color: GOLD,
          letterSpacing: "0.04em",
        }}>COST IMPACT</span>
      </div>
      <div style={{
        display: "flex", alignItems: "baseline", gap: 12, marginBottom: 6, flexWrap: "wrap",
      }}>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 28, fontWeight: 700,
          color: TEXT_DIM, textDecoration: "line-through", textDecorationColor: "rgba(148,163,184,0.4)",
        }}>
          ${cost.monthly_before.toFixed(2)}
        </span>
        <span style={{ fontSize: 20, color: TEXT_DIM }}>→</span>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 32, fontWeight: 700, color: GREEN,
        }}>
          <AnimatedNumber value={cost.monthly_after} prefix="$" />
        </span>
        <span style={{ fontSize: 13, color: TEXT_DIM }}>/month</span>
      </div>
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        background: isDown ? GREEN_DIM : RED_DIM,
        border: `1px solid ${isDown ? GREEN : RED}33`,
        borderRadius: 6, padding: "4px 12px", marginBottom: 20,
      }}>
        <span style={{ fontSize: 16, color: isDown ? GREEN : RED }}>
          {isDown ? "↓" : "↑"}
        </span>
        <span style={{
          fontFamily: "'JetBrains Mono', monospace", fontSize: 14, fontWeight: 600,
          color: isDown ? GREEN : RED,
        }}>
          {Math.abs(pctChange).toFixed(1)}%
        </span>
        {monthSaved > 0 && (
          <span style={{ fontSize: 12, color: GREEN, opacity: 0.8 }}>
            · saving ${monthSaved.toFixed(2)}/mo
          </span>
        )}
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MiniStat label="Per Cycle" before={cost.total_before} after={cost.total_after} />
        <MiniStat label="Daily" before={cost.daily_before} after={cost.daily_after} />
      </div>
      <div style={{ marginTop: 20 }}>
        <div style={{ fontSize: 11, color: TEXT_DIM, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Per-Soul Breakdown
        </div>
        {cost.souls.filter(s => s.before !== null).map(s => {
          const max = Math.max(...cost.souls.filter(x => x.before !== null).map(x => x.before));
          const wBefore = (s.before / max) * 100;
          const wAfter = s.after !== null ? (s.after / max) * 100 : 0;
          return (
            <div key={s.name} style={{ marginBottom: 10 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: TEXT }}>
                  {s.name}
                </span>
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: TEXT_DIM }}>
                  ${(s.before * 1000).toFixed(2)} → {s.after !== null ? `$${(s.after * 1000).toFixed(2)}` : "removed"}
                </span>
              </div>
              <div style={{ position: "relative", height: 6, background: "rgba(255,255,255,0.04)", borderRadius: 3 }}>
                <div style={{
                  position: "absolute", height: "100%", borderRadius: 3,
                  width: `${wBefore}%`, background: "rgba(148,163,184,0.2)",
                }} />
                <div style={{
                  position: "absolute", height: "100%", borderRadius: 3,
                  width: `${wAfter}%`,
                  background: s.after === null ? RED : (s.after < s.before ? GREEN : GOLD),
                  transition: "width 0.8s cubic-bezier(0.16,1,0.3,1)",
                }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MiniStat({ label, before, after }) {
  return (
    <div style={{
      background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "8px 14px", flex: "1 1 100px",
    }}>
      <div style={{ fontSize: 10, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: TEXT }}>
        <span style={{ opacity: 0.5, textDecoration: "line-through" }}>${before.toFixed(4)}</span>
        {" → "}
        <span style={{ color: after < before ? GREEN : RED }}>${after.toFixed(4)}</span>
      </div>
    </div>
  );
}

function TierChangeCard({ cost }) {
  const changes = cost.souls.filter(s => s.tier_before !== s.tier_after && s.tier_after !== null);
  const removed = cost.souls.filter(s => s.tier_after === null);
  if (changes.length === 0 && removed.length === 0) return null;

  const tierColor = (t) => {
    if (!t) return TEXT_DIM;
    if (t.includes("0A")) return "#a78bfa";
    if (t.includes("0B")) return "#60a5fa";
    if (t === "Tier1") return "#34d399";
    if (t === "Tier2") return "#fbbf24";
    if (t === "Tier3") return TEXT_DIM;
    if (t === "Groq") return "#f97316";
    if (t === "Cerebras") return "#22d3ee";
    if (t === "Together") return "#a78bfa";
    if (t === "Fireworks") return "#ef4444";
    return GOLD;
  };

  return (
    <div style={{
      background: BG_CARD, border: `1px solid ${GOLD_BORDER}`, borderRadius: 12,
      padding: 24, flex: "1 1 280px", minWidth: 260,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <span style={{ fontSize: 18 }}>⬡</span>
        <span style={{
          fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 600, color: GOLD,
          letterSpacing: "0.04em",
        }}>MIND / TIER CHANGES</span>
      </div>
      {changes.map(s => (
        <div key={s.name} style={{
          display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap",
        }}>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: TEXT, minWidth: 70,
          }}>{s.name}</span>
          <TierPill tier={s.tier_before} color={tierColor(s.tier_before)} dimmed />
          <span style={{ color: TEXT_DIM, fontSize: 16 }}>→</span>
          <TierPill tier={s.tier_after} color={tierColor(s.tier_after)} />
        </div>
      ))}
      {removed.map(s => (
        <div key={s.name} style={{
          display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap",
        }}>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: TEXT_DIM,
            textDecoration: "line-through", minWidth: 70,
          }}>{s.name}</span>
          <TierPill tier={s.tier_before} color={tierColor(s.tier_before)} dimmed />
          <span style={{ color: TEXT_DIM, fontSize: 16 }}>→</span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: RED,
            background: RED_DIM, padding: "3px 10px", borderRadius: 4,
            border: `1px solid ${RED}33`,
          }}>REMOVED</span>
        </div>
      ))}
    </div>
  );
}

function TierPill({ tier, color, dimmed = false }) {
  return (
    <span style={{
      fontFamily: "'JetBrains Mono', monospace", fontSize: 12, fontWeight: 600,
      color: dimmed ? `${color}88` : color,
      background: `${color}${dimmed ? "0a" : "18"}`,
      border: `1px solid ${color}${dimmed ? "22" : "44"}`,
      padding: "4px 12px", borderRadius: 6,
      opacity: dimmed ? 0.6 : 1,
    }}>{tier}</span>
  );
}

function TopologyCard({ topology }) {
  const hasChanges = topology.added.length > 0 || topology.removed.length > 0 || topology.modified.length > 0;
  if (!hasChanges) return null;
  return (
    <div style={{
      background: BG_CARD, border: `1px solid ${GOLD_BORDER}`, borderRadius: 12,
      padding: 24, flex: "1 1 260px", minWidth: 240,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <span style={{ fontSize: 18 }}>◇</span>
        <span style={{
          fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 600, color: GOLD,
          letterSpacing: "0.04em",
        }}>TOPOLOGY</span>
      </div>
      {topology.removed.map(s => (
        <DiffLine key={`r-${s}`} icon="−" color={RED} label={s} detail="Soul removed" />
      ))}
      {topology.added.map(s => (
        <DiffLine key={`a-${s}`} icon="+" color={GREEN} label={s} detail="Soul added" />
      ))}
      {topology.modified.map(s => (
        <DiffLine key={`m-${s}`} icon="~" color={AMBER} label={s} detail="Modified" />
      ))}
      {topology.route_changes.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid rgba(255,255,255,0.06)" }}>
          <div style={{ fontSize: 10, color: TEXT_DIM, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>
            Route Changes
          </div>
          {topology.route_changes.map((r, i) => (
            <div key={i} style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: TEXT_DIM, marginBottom: 4,
            }}>
              <span style={{ color: r.type === "removed" ? RED : GREEN }}>
                {r.type === "removed" ? "−" : "+"}
              </span>{" "}
              {r.from || r.to}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DiffLine({ icon, color, label, detail }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 10, marginBottom: 10,
      padding: "6px 10px", borderRadius: 6, background: `${color}08`,
    }}>
      <span style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 16, fontWeight: 700,
        color, width: 18, textAlign: "center",
      }}>{icon}</span>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 13, color: TEXT, fontWeight: 600 }}>
        {label}
      </span>
      <span style={{ fontSize: 11, color: TEXT_DIM, marginLeft: "auto" }}>{detail}</span>
    </div>
  );
}

function CapabilitiesCard({ capabilities, memory }) {
  const hasData = capabilities.senses_added.length > 0 || capabilities.senses_removed.length > 0 ||
    memory.fields_added.length > 0 || memory.fields_removed.length > 0;
  if (!hasData) return null;
  return (
    <div style={{
      background: BG_CARD, border: `1px solid ${GOLD_BORDER}`, borderRadius: 12,
      padding: 24, flex: "1 1 260px", minWidth: 240,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        <span style={{ fontSize: 18 }}>⎔</span>
        <span style={{
          fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 600, color: GOLD,
          letterSpacing: "0.04em",
        }}>CAPABILITIES & MEMORY</span>
      </div>
      {capabilities.senses_added.map((s, i) => (
        <DiffLine key={`sa-${i}`} icon="+" color={GREEN} label={`${s.soul}.${s.sense}`} detail="sense added" />
      ))}
      {capabilities.senses_removed.map((s, i) => (
        <DiffLine key={`sr-${i}`} icon="−" color={RED} label={`${s.soul}.${s.sense}`} detail="sense removed" />
      ))}
      {(capabilities.senses_added.length > 0 || capabilities.senses_removed.length > 0) &&
        (memory.fields_added.length > 0 || memory.fields_removed.length > 0) && (
          <div style={{ height: 1, background: "rgba(255,255,255,0.06)", margin: "12px 0" }} />
        )}
      {memory.fields_added.map((f, i) => (
        <DiffLine key={`fa-${i}`} icon="+" color={CYAN} label={`${f.soul}.${f.field}`} detail={f.type} />
      ))}
      {memory.fields_removed.map((f, i) => (
        <DiffLine key={`fr-${i}`} icon="−" color={RED} label={`${f.soul}.${f.field}`} detail={f.type} />
      ))}
    </div>
  );
}

function FindingsLog({ findings }) {
  const [filter, setFilter] = useState("ALL");
  const filtered = filter === "ALL" ? findings : findings.filter(f => f.severity === filter);
  return (
    <div style={{
      background: BG_CARD, border: `1px solid ${GOLD_BORDER}`, borderRadius: 12,
      padding: 24,
    }}>
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        marginBottom: 16, flexWrap: "wrap", gap: 10,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 18 }}>⊞</span>
          <span style={{
            fontFamily: "'Playfair Display', serif", fontSize: 16, fontWeight: 600, color: GOLD,
            letterSpacing: "0.04em",
          }}>ALL FINDINGS</span>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {["ALL", "CRITICAL", "WARNING", "INFO"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              background: filter === f ? GOLD_DIM : "transparent",
              border: `1px solid ${filter === f ? GOLD_BORDER : "rgba(255,255,255,0.08)"}`,
              borderRadius: 4, padding: "4px 10px", cursor: "pointer",
              fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
              color: filter === f ? GOLD : TEXT_DIM, letterSpacing: "0.04em",
            }}>{f}</button>
          ))}
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {filtered.map((f, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
            borderRadius: 6, background: "rgba(255,255,255,0.02)",
            borderLeft: `3px solid ${f.severity === "CRITICAL" ? RED : f.severity === "WARNING" ? AMBER : BLUE}`,
            flexWrap: "wrap",
          }}>
            <SeverityBadge severity={f.severity} />
            <span style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: TEXT_DIM, minWidth: 60,
            }}>{f.code}</span>
            <span style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: PURPLE, minWidth: 70,
            }}>{f.category}</span>
            <span style={{ fontSize: 13, color: TEXT, flex: 1 }}>{f.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function BehavioralDiffVisualizer({ data }) {
  const diff = data || MOCK_DIFF;

  return (
    <div style={{
      background: BG_DEEP, color: TEXT, padding: 24, minHeight: "100vh",
      fontFamily: "'DM Sans', sans-serif",
    }}>
      <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=JetBrains+Mono:wght@400;600;700&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet" />

      <div style={{ maxWidth: 1100, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 12, marginBottom: 4,
        }}>
          <span style={{
            fontFamily: "'Playfair Display', serif", fontSize: 13, color: GOLD,
            letterSpacing: "0.12em", textTransform: "uppercase", opacity: 0.7,
          }}>NOUS</span>
          <span style={{ color: "rgba(255,255,255,0.15)" }}>·</span>
          <span style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: TEXT_DIM,
          }}>Behavioral Diff Engine</span>
        </div>

        <VerdictBanner verdict={diff.verdict} source={diff.source} target={diff.target} />

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <CostImpactCard cost={diff.cost} />
          <TierChangeCard cost={diff.cost} />
        </div>

        <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
          <TopologyCard topology={diff.topology} />
          <CapabilitiesCard capabilities={diff.capabilities} memory={diff.memory} />
        </div>

        <FindingsLog findings={diff.findings} />
      </div>
    </div>
  );
}
