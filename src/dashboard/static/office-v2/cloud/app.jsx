// App shell — header, scene canvas with motion + hit overlays, side panel,
// floating action callouts, activity ticker, tweaks panel.

const { useState, useEffect, useRef, useMemo } = React;

const ACTIONS = [
  { id: "fanout", from: "nickfury",      to: "portfolio",     label: "ASSIGN BOOK",   color: "#22c55e" },
  { id: "synth",  from: "superman",      to: "vision",        label: "FORWARD SIGNAL", color: "#38bdf8" },
  { id: "exec",   from: "vision",        to: "ironman",       label: "EXECUTE PLAN",  color: "#fb923c" },
  { id: "watch",  from: "ironman",       to: "batman",        label: "RISK CHECK",    color: "#facc15" },
  { id: "report", from: "portfolio",     to: "dailypnl",      label: "WRITE PNL",     color: "#a78bfa" },
  { id: "search", from: "doctorstrange", to: "__search",      label: "SEARCH WEB",    color: "#38bdf8" },
];

const ANCHORS = {
  __search: { x: 471, y: 110 },
};

function getAnchor(id) {
  if (ANCHORS[id]) return ANCHORS[id];
  const station = STATIONS.find(s => s.id === id);
  if (!station) return { x: SCENE_W/2, y: SCENE_H/2 };
  const pos = agentPosFor(station);
  return { x: pos.x + 8, y: pos.y - 2 };
}

function App() {
  const canvasRef = useRef(null);
  const motionRef = useRef(makeInitialMotion());
  const flashesRef = useRef({}); // stationId → { color, label, until }
  const [frame, setFrame] = useState(0);
  const [selected, setSelected] = useState("nickfury");
  const [feedEvents, setFeedEvents] = useState([]);
  const [agentTasks, setAgentTasks] = useState({});
  const [tweaks, setTweaks] = useTweaks(/*EDITMODE-BEGIN*/{
    "scale": 3,
    "showLabels": true,
    "showActions": true,
    "showMotion": true,
    "maxAway": 3,
    "showPoiMarkers": true,
    "mode": "active"
  }/*EDITMODE-END*/);

  // Initial data load + subscriptions to live data layer
  useEffect(() => {
    fetchFeedEvents().then(setFeedEvents);
    fetchAgentTasks().then(setAgentTasks);
    const unsubTrade = subscribeTradeEvents((ev) => {
      // Flash this station's monitor
      flashesRef.current[ev.stationId] = {
        color: ev.side === "win" ? "#22c55e" : "#ef4444",
        label: (ev.pnl >= 0 ? "+" : "") + ev.pnl + "%",
        until: 18, // ~1.4s
        max: 18,
      };
      // Push to feed
      const agent = AGENTS.find(a => a.id === ev.stationId);
      const time = new Date().toTimeString().slice(0,8);
      const msg = `${ev.side==="win"?"CLOSED +":"CLOSED "}${ev.pnl}% on ${ev.sym} (${ev.size} clip)`;
      setFeedEvents(prev => [{ t: time, who: agent?.name || ev.stationId, msg }, ...prev].slice(0, 24));
    });
    const unsubTask = subscribeAgentTasks((ev) => {
      setAgentTasks(prev => ({ ...prev, [ev.agentId]: ev.task }));
    });
    return () => { unsubTrade(); unsubTask(); };
  }, []);
  useEffect(() => {
    let raf, last = 0, tick = 0;
    function loop(t) {
      if (t - last > 80) {
        tick++; last = t;
        if (tweaks.showMotion) {
          tickMotion(motionRef.current, tick, { maxAway: Number(tweaks.maxAway) });
        }
        // Decay flashes
        const fl = flashesRef.current;
        for (const k in fl) {
          fl[k].until -= 1;
          if (fl[k].until <= 0) delete fl[k];
        }
        setFrame(tick);
      }
      raf = requestAnimationFrame(loop);
    }
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [tweaks.showMotion, tweaks.maxAway]);

  // Render to canvas every frame
  useEffect(() => {
    const cvs = canvasRef.current; if (!cvs) return;
    const ctx = cvs.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    // Build flash snapshot with normalized intensity
    const flashSnap = {};
    for (const k in flashesRef.current) {
      const f = flashesRef.current[k];
      flashSnap[k] = { color: f.color, label: f.label, intensity: f.until / f.max };
    }
    paintScene(ctx, frame, AGENTS, motionRef.current, {
      showPoiMarkers: tweaks.showPoiMarkers,
      flashes: flashSnap,
    });
  }, [frame, tweaks.showPoiMarkers]);

  const selectedAgent = AGENTS.find(a => a.id === selected) || AGENTS[0];
  const liveTask = agentTasks[selectedAgent.id] || selectedAgent.task;
  const scale = Number(tweaks.scale) || 3;

  const feedEventsLegacy = useMemo(() => [], []);

  // Build a snapshot of motion to drive the React-side overlays (labels, hits)
  // We re-read motionRef on every frame.
  const motion = motionRef.current;

  return (
    <div className="page">
      <header className="hdr">
        <div className="hdr-l">
          <div className="hdr-eyebrow">MEKKA OPS · L4 COMMAND</div>
          <h1>Mekka Pixel Office</h1>
          <div className="hdr-sub">Self-growing AI trading floor · {AGENTS.length} agents on duty</div>
        </div>
        <div className="hdr-r">
          <div className={`pill ${tweaks.mode === 'active' ? 'pill-on' : 'pill-off'}`}>
            <span className="dot"></span>
            {tweaks.mode === 'active' ? 'MARKET LIVE' : 'STAND-DOWN'}
          </div>
          <div className="pill pill-muted">PAPER · testnet</div>
          <div className="pill pill-muted">UPTIME 04:12:38</div>
        </div>
      </header>

      <div className="main">
        <div className="scene-col">
          <div className="scene-frame">
            <div className="scene-frame-hdr">
              <div className="frame-tabs">
                <span className="tab active">Pixel Office</span>
                <span className="tab">Layer Map</span>
                <span className="tab">Roster</span>
              </div>
              <div className="frame-legend">
                <span><i style={{background:"#38bdf8"}}/> L1 Analysis</span>
                <span><i style={{background:"#a78bfa"}}/> L2 Strategy</span>
                <span><i style={{background:"#fb923c"}}/> L3 Risk/Exec</span>
                <span><i style={{background:"#22c55e"}}/> L4 Command</span>
              </div>
            </div>

            <div className="scene-wrap" style={{
              width: SCENE_W * scale, height: SCENE_H * scale,
            }}>
              <canvas ref={canvasRef} width={SCENE_W} height={SCENE_H}
                      style={{ width: SCENE_W * scale, height: SCENE_H * scale }} />

              {tweaks.showActions && (
                <svg className="action-svg" viewBox={`0 0 ${SCENE_W} ${SCENE_H}`}
                     preserveAspectRatio="none"
                     style={{ width: SCENE_W * scale, height: SCENE_H * scale }}>
                  <defs>
                    {ACTIONS.map(a => (
                      <marker key={a.id} id={`arr-${a.id}`} viewBox="0 0 8 8" refX="6" refY="4"
                              markerWidth="6" markerHeight="6" orient="auto">
                        <path d="M0,0 L8,4 L0,8 L2,4 Z" fill={a.color} />
                      </marker>
                    ))}
                  </defs>
                  {ACTIONS.map(a => {
                    const f = getAnchor(a.from), t = getAnchor(a.to);
                    const dash = (frame * 2) % 12;
                    return (
                      <line key={a.id} x1={f.x} y1={f.y} x2={t.x} y2={t.y}
                            stroke={a.color} strokeWidth="1.5" strokeDasharray="4 3"
                            strokeDashoffset={-dash} markerEnd={`url(#arr-${a.id})`}
                            opacity="0.85" />
                    );
                  })}
                </svg>
              )}

              {tweaks.showLabels && AGENTS.map(a => {
                const m = motion[a.id]; if (!m) return null;
                const isSel = a.id === selected;
                return (
                  <button
                    key={a.id}
                    className={`agent-label ${isSel ? 'sel' : ''} ${m.mode!=='at-desk' ? 'walking' : ''}`}
                    style={{
                      left: (m.pos.x + 6) * scale,
                      top: (m.pos.y - 14) * scale,
                      borderColor: a.color,
                      color: a.color,
                    }}
                    onClick={() => setSelected(a.id)}
                  >
                    {a.name.toUpperCase()}
                  </button>
                );
              })}

              {tweaks.showActions && ACTIONS.map(a => {
                const f = getAnchor(a.from), t = getAnchor(a.to);
                const mx = (f.x + t.x) / 2, my = (f.y + t.y) / 2;
                return (
                  <div key={`lbl-${a.id}`} className="action-lbl"
                       style={{ left: mx * scale, top: my * scale,
                                color: a.color, borderColor: a.color }}>
                    {a.label}
                  </div>
                );
              })}

              {/* POI labels */}
              {tweaks.showPoiMarkers && POIS.map(p => (
                <div key={p.id} className="poi-lbl"
                     style={{ left: p.x * scale, top: (p.y + 22) * scale }}>
                  {p.label}
                </div>
              ))}

              {AGENTS.map(a => {
                const m = motion[a.id]; if (!m) return null;
                return (
                  <div key={`hit-${a.id}`} className="agent-hit"
                       onClick={() => setSelected(a.id)}
                       style={{
                         left: m.pos.x * scale, top: m.pos.y * scale,
                         width: 16 * scale, height: 22 * scale,
                       }} />
                );
              })}
            </div>

            <div className="scene-caption">
              <span className="cap-key">L1 → L2 → L3 → L4</span>
              <span className="cap-sep">·</span>
              <span>Agents leave their desks for coffee, the wall TV, or the whiteboard. Click anyone for detail.</span>
            </div>
          </div>

          <div className="ticker">
            <div className="ticker-hdr">
              <span className="ticker-dot"></span>
              <span>HERO AUDIT STREAM</span>
              <span className="ticker-spacer"></span>
              <span className="ticker-meta">{feedEvents.length} events · 5s window</span>
            </div>
            <div className="ticker-body">
              {feedEvents.map((e, i) => (
                <div key={i} className="ticker-row">
                  <span className="t-time">{e.t}</span>
                  <span className="t-who">{e.who}</span>
                  <span className="t-msg">{e.msg}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="side">
          <div className="agent-card" style={{borderColor: selectedAgent.color}}>
            <div className="agent-card-top">
              <div className="agent-portrait">
                <AgentPortrait agent={selectedAgent} />
              </div>
              <div>
                <div className="agent-layer" style={{color: selectedAgent.color}}>
                  {selectedAgent.layer} · {selectedAgent.role}
                </div>
                <div className="agent-name">{selectedAgent.name}</div>
                <div className="agent-status">
                  <span className="status-dot" style={{background: selectedAgent.color}}></span>
                  {motion[selectedAgent.id]?.mode === 'at-desk' ? 'AT DESK' :
                   motion[selectedAgent.id]?.mode === 'walking' ? 'WALKING' :
                   motion[selectedAgent.id]?.mode === 'visiting' ? 'VISITING ' + (motion[selectedAgent.id]?.poi||'').toUpperCase() :
                   'RETURNING'}
                </div>
              </div>
            </div>
            <p className="agent-summary">{selectedAgent.summary}</p>
            <div className="agent-task">
              <div className="task-lbl">CURRENT TASK</div>
              <div className="task-val">{liveTask}</div>
            </div>
            <div className="agent-stats">
              <div className="stat">
                <div className="stat-val">{42 + (selectedAgent.name.length*3)%50}</div>
                <div className="stat-lbl">tasks today</div>
              </div>
              <div className="stat">
                <div className="stat-val">{93 + (selectedAgent.name.length)%6}%</div>
                <div className="stat-lbl">success</div>
              </div>
              <div className="stat">
                <div className="stat-val">{120 + (selectedAgent.name.length*11)%80}ms</div>
                <div className="stat-lbl">p50 latency</div>
              </div>
            </div>
            <div className="agent-actions">
              <button className="btn btn-primary">Open transcript</button>
              <button className="btn">Pause</button>
              <button className="btn btn-danger">Kill</button>
            </div>
          </div>

          <div className="roster">
            <div className="roster-hdr">ROSTER · {AGENTS.length} agents</div>
            <div className="roster-grid">
              {AGENTS.map(a => (
                <button key={a.id}
                        className={`roster-cell ${a.id===selected?'sel':''}`}
                        onClick={() => setSelected(a.id)}
                        style={{borderColor: a.id===selected?a.color:"transparent"}}>
                  <div className="rc-portrait"><AgentPortrait agent={a} small /></div>
                  <div className="rc-meta">
                    <div className="rc-name">{a.name}</div>
                    <div className="rc-layer" style={{color:a.color}}>
                      {a.layer} · {(motion[a.id]?.mode || 'at-desk')}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </aside>
      </div>

      <TweaksPanel title="Tweaks">
        <TweakSection title="Display">
          <TweakRadio label="Scale" value={String(tweaks.scale)}
                      options={[{value:"2",label:"2×"},{value:"3",label:"3×"},{value:"4",label:"4×"}]}
                      onChange={(v)=>setTweaks({scale: Number(v)})} />
          <TweakToggle label="Show labels" value={tweaks.showLabels}
                       onChange={(v)=>setTweaks({showLabels:v})} />
          <TweakToggle label="Show action arrows" value={tweaks.showActions}
                       onChange={(v)=>setTweaks({showActions:v})} />
          <TweakToggle label="POI floor markers" value={tweaks.showPoiMarkers}
                       onChange={(v)=>setTweaks({showPoiMarkers:v})} />
        </TweakSection>
        <TweakSection title="Agent activity">
          <TweakToggle label="Agents wander" value={tweaks.showMotion}
                       onChange={(v)=>setTweaks({showMotion:v})} />
          <TweakSlider label="Max away from desk" value={Number(tweaks.maxAway)}
                       min={0} max={6} step={1}
                       onChange={(v)=>setTweaks({maxAway:v})} />
          <TweakRadio label="Mode" value={tweaks.mode}
                      options={[{value:"active",label:"Live"},{value:"standby",label:"Stand-down"}]}
                      onChange={(v)=>setTweaks({mode:v})} />
        </TweakSection>
      </TweaksPanel>
    </div>
  );
}

function AgentPortrait({ agent, small }) {
  const ref = useRef(null);
  useEffect(() => {
    const c = ref.current; if (!c) return;
    const ctx = c.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0,0,16,22);
    drawAgent(ctx, agent, 0, 0);
  }, [agent]);
  const px = small ? 3 : 5;
  return <canvas ref={ref} width={16} height={22}
                 style={{width:16*px, height:22*px, imageRendering:"pixelated"}} />;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
