import React, { useEffect, useMemo, useState } from 'react';
import OfficeScene from './scene.jsx';
import { AGENTS, normalizeAgentId } from './roster.js';

const TEXT = {
  pt: {
    title: 'Mekka Pixel Office V2',
    subtitle: 'Escritório tático 3D pixel art integrado aos agentes',
    stream: 'Hero Audit Stream',
    roster: 'Roster de Agentes',
    task: 'Tarefa Atual',
    mode: 'Modo',
    active: 'Ativo',
    standby: 'Stand-by',
  },
  en: {
    title: 'Mekka Pixel Office V2',
    subtitle: '3D pixel tactical office integrated with agents',
    stream: 'Hero Audit Stream',
    roster: 'Agent Roster',
    task: 'Current Task',
    mode: 'Mode',
    active: 'Active',
    standby: 'Stand-by',
  },
};

export default function OfficeApp({ theme = 'dark', language = 'pt', dataProvider }) {
  const [selectedId, setSelectedId] = useState('nick_fury');
  const [feedEvents, setFeedEvents] = useState([]);
  const [tasks, setTasks] = useState({});
  const [liveState, setLiveState] = useState({});

  const t = TEXT[language] || TEXT.pt;

  useEffect(() => {
    let unsubTrades = () => {};
    let unsubTasks = () => {};

    async function boot() {
      const [initialTasks, initialFeed] = await Promise.all([
        dataProvider.getAgentTasks(),
        dataProvider.getAuditFeed(28),
      ]);
      setTasks(initialTasks || {});
      setFeedEvents(initialFeed || []);

      unsubTrades = dataProvider.subscribeTradeEvents((ev) => {
        const normalized = normalizeAgentId(ev.stationId);
        const who = AGENTS.find((a) => a.id === normalized)?.name || ev.stationId;
        const msg = `${ev.side === 'loss' ? 'CLOSED' : 'CLOSED +'} ${ev.pnl}% on ${ev.sym} (${ev.size})`;
        setFeedEvents((prev) => ([{ t: new Date().toLocaleTimeString('pt-BR', { hour12: false }), who, msg }, ...prev]).slice(0, 40));
        setLiveState((prev) => ({
          ...prev,
          [normalized]: {
            ...(prev[normalized] || {}),
            side: ev.side,
            flashLabel: `${ev.pnl > 0 ? '+' : ''}${ev.pnl}%`,
            flashUntil: Date.now() + 2200,
            walkOffsetX: ev.side === 'loss' ? -2 : 2,
            walkOffsetY: -1,
          },
        }));
      });

      unsubTasks = dataProvider.subscribeAgentUpdates((ev) => {
        const normalized = normalizeAgentId(ev.agentId);
        setTasks((prev) => ({ ...prev, [normalized]: ev.task }));
      });
    }

    boot();
    return () => {
      unsubTrades();
      unsubTasks();
    };
  }, [dataProvider]);

  const selectedAgent = useMemo(() => AGENTS.find((a) => a.id === selectedId) || AGENTS[0], [selectedId]);

  return (
    <div className={`office-v2-shell ${theme === 'light' ? 'theme-light' : 'theme-dark'}`}>
      <div className="office-v2-head">
        <div>
          <h3>{t.title}</h3>
          <p>{t.subtitle}</p>
        </div>
        <div className="office-v2-mode">{t.mode}: <strong>{feedEvents.length ? t.active : t.standby}</strong></div>
      </div>

      <div className="office-v2-grid">
        <div className="office-v2-scene-wrap">
          <OfficeScene selectedId={selectedId} liveState={liveState} theme={theme} />
          <div className="office-v2-feed">
            <div className="feed-title">{t.stream}</div>
            <div className="feed-body">
              {feedEvents.map((row, idx) => (
                <div className="feed-row" key={`${row.t}-${idx}`}>
                  <span>{row.t}</span>
                  <strong>{row.who}</strong>
                  <span>{row.msg}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <aside className="office-v2-side">
          <div className="agent-card">
            <div className="agent-name" style={{ color: selectedAgent.color }}>{selectedAgent.name}</div>
            <div className="agent-role">{selectedAgent.layer} · {selectedAgent.role}</div>
            <div className="agent-task-title">{t.task}</div>
            <div className="agent-task-text">{tasks[selectedAgent.id] || 'Monitoring mission pipeline'}</div>
          </div>

          <div className="roster-title">{t.roster}</div>
          <div className="roster-list">
            {AGENTS.map((agent) => (
              <button
                type="button"
                key={agent.id}
                className={`roster-item ${agent.id === selectedId ? 'active' : ''}`}
                onClick={() => setSelectedId(agent.id)}
              >
                <span className="dot" style={{ backgroundColor: agent.color }} />
                <span>{agent.name}</span>
                <small>{agent.layer}</small>
              </button>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}
