export const AGENTS = [
  { id: 'superman', name: 'Superman', layer: 'L1', role: 'Market Analysis', color: '#3b82f6', outfit: 'blue_red' },
  { id: 'doctor_strange', name: 'Doctor Strange', layer: 'L1', role: 'Macro Probability', color: '#a855f7', outfit: 'purple_red' },
  { id: 'black_panther', name: 'Black Panther', layer: 'L1', role: 'Onchain Intelligence', color: '#64748b', outfit: 'black_vibranium' },
  { id: 'thor', name: 'Thor', layer: 'L1', role: 'Volatility Engine', color: '#60a5fa', outfit: 'steel_blue' },
  { id: 'aquaman', name: 'Aquaman', layer: 'L1', role: 'Liquidity Analyst', color: '#14b8a6', outfit: 'green_gold' },
  { id: 'spider_man', name: 'Spider-Man', layer: 'L1', role: 'Anomaly Detector', color: '#ef4444', outfit: 'red_blue' },
  { id: 'vision', name: 'Vision', layer: 'L2', role: 'Predictive Analyst', color: '#f59e0b', outfit: 'green_gold' },
  { id: 'professor_x', name: 'Professor X', layer: 'L2', role: 'Swarm Coordinator', color: '#818cf8', outfit: 'navy_gray' },
  { id: 'batman', name: 'Batman', layer: 'L3', role: 'Risk Guardian', color: '#fbbf24', outfit: 'dark_yellow' },
  { id: 'iron_man', name: 'Iron Man', layer: 'L3', role: 'Execution Engineer', color: '#f97316', outfit: 'red_gold' },
  { id: 'nick_fury', name: 'Nick Fury', layer: 'L4', role: 'Mission Commander', color: '#22c55e', outfit: 'black_trench' },
  { id: 'portfolio_manager', name: 'Portfolio Manager', layer: 'L4', role: 'Snapshot Service', color: '#16a34a', outfit: 'blue_formal' },
  { id: 'wolverine', name: 'Wolverine', layer: 'L4', role: 'Recovery Agent', color: '#eab308', outfit: 'yellow_blue' },
  { id: 'flash', name: 'Flash', layer: 'L1.5', role: 'Momentum Scalper', color: '#ef4444', outfit: 'red_lightning' },
  { id: 'deadpool', name: 'Deadpool', layer: 'Pending', role: 'Chaos Simulator', color: '#dc2626', outfit: 'red_black' },
  // Cyclops (Story 046) — SL/TP monitor for paper positions. Visor overlay.
  { id: 'cyclops', name: 'Cyclops', layer: 'L3', role: 'SL/TP Monitor', color: '#ef4444', outfit: 'red_blue_visor' },
  // Beast (Story 248 / codex M40) — read-only continuous-improvement
  // analyst. Sits in L4 (analyst tier) alongside Wolverine and PortfolioManager.
  { id: 'beast', name: 'Beast', layer: 'L4', role: 'Continuous Improvement', color: '#38bdf8', outfit: 'blue_fur_labcoat' },
  // Continuous-Improvement squad scanners (read-only). Cypher/Domino/Forge are
  // the hero codenames for the CodeAuditor/RiskScanner/OpsScanner agents; Ice
  // Man = ExternalResearcher; Sage = measurement loop.
  { id: 'cypher', name: 'Cypher', layer: 'L4', role: 'Code Auditor', color: '#10b981', outfit: 'green_black' },
  { id: 'domino', name: 'Domino', layer: 'L4', role: 'Risk Scanner', color: '#cbd5e1', outfit: 'black_white' },
  { id: 'forge', name: 'Forge', layer: 'L4', role: 'Ops Scanner', color: '#fb923c', outfit: 'red_tech' },
  { id: 'ice_man', name: 'Ice Man', layer: 'L4', role: 'External Research', color: '#7dd3fc', outfit: 'ice_blue' },
  { id: 'sage', name: 'Sage', layer: 'L4', role: 'Measurement / KPI', color: '#06b6d4', outfit: 'data_shades' },
  // Continuous-Improvement / vault curation crew.
  { id: 'jean_grey', name: 'Jean Grey', layer: 'L4', role: 'Vault Curator', color: '#f43f5e', outfit: 'red_telepath' },
  { id: 'mentor', name: 'Mentor', layer: 'L4', role: 'Self-Improvement Loop', color: '#a3a3a3', outfit: 'silver_robe' },
  // Strategy-tier auxiliaries.
  { id: 'vision_critic', name: 'Vision Critic', layer: 'L2', role: 'Second-Look Reviewer', color: '#fcd34d', outfit: 'green_gold_visor' },
  { id: 'vision_moa', name: 'Vision MoA', layer: 'L2', role: 'Mixture of Agents', color: '#fde68a', outfit: 'green_gold_trio' },
  // Operator-facing concierge + cosmic risk archetype.
  { id: 'mekka', name: 'Mekka', layer: 'L4', role: 'Operator Concierge', color: '#facc15', outfit: 'crown_gold' },
  { id: 'galactus', name: 'Galactus', layer: 'L4', role: 'Premortem Devourer', color: '#7c3aed', outfit: 'purple_cosmic' },
  // Prometheus — observer/learning agent (read-only, NOT a trader).
  { id: 'prometheus', name: 'Prometheus', layer: 'Dev/QA', role: 'Prompt Auditor & Observer', color: '#f97316', outfit: 'orange_flame' },
];

export const STATIONS = [
  { id: 'superman', x: 50, y: 80 },
  { id: 'doctor_strange', x: 140, y: 80 },
  { id: 'black_panther', x: 230, y: 80 },
  { id: 'thor', x: 320, y: 80 },
  { id: 'aquaman', x: 410, y: 80 },
  { id: 'spider_man', x: 500, y: 80 },
  { id: 'vision', x: 95, y: 175 },
  { id: 'professor_x', x: 185, y: 175 },
  { id: 'batman', x: 275, y: 175 },
  { id: 'iron_man', x: 365, y: 175 },
  { id: 'nick_fury', x: 455, y: 175 },
  { id: 'portfolio_manager', x: 545, y: 175 },
  { id: 'wolverine', x: 140, y: 265 },
  { id: 'flash', x: 320, y: 265 },
  { id: 'deadpool', x: 500, y: 265 },
  // Row 4 — newer arrivals: Cyclops (monitor) and Beast (analyst).
  { id: 'cyclops', x: 230, y: 355 },
  { id: 'beast', x: 410, y: 355 },
  // Row 5 — Continuous-Improvement squad scanners.
  { id: 'cypher', x: 50, y: 445 },
  { id: 'domino', x: 140, y: 445 },
  { id: 'forge', x: 230, y: 445 },
  { id: 'ice_man', x: 320, y: 445 },
  { id: 'sage', x: 410, y: 445 },
  { id: 'jean_grey', x: 500, y: 445 },
  // Row 6 — Strategy auxiliaries + curation + Prometheus.
  { id: 'vision_critic', x: 50, y: 535 },
  { id: 'vision_moa', x: 140, y: 535 },
  { id: 'mentor', x: 230, y: 535 },
  { id: 'mekka', x: 320, y: 535 },
  { id: 'galactus', x: 410, y: 535 },
  { id: 'prometheus', x: 500, y: 535 },
];

export const AGENT_ID_MAP = {
  superman: 'superman',
  doctorstrange: 'doctor_strange',
  doctor_strange: 'doctor_strange',
  blackpanther: 'black_panther',
  black_panther: 'black_panther',
  thor: 'thor',
  aquaman: 'aquaman',
  spiderman: 'spider_man',
  spider_man: 'spider_man',
  vision: 'vision',
  professorx: 'professor_x',
  professor_x: 'professor_x',
  batman: 'batman',
  ironman: 'iron_man',
  iron_man: 'iron_man',
  nickfury: 'nick_fury',
  nick_fury: 'nick_fury',
  portfolio: 'portfolio_manager',
  portfolio_manager: 'portfolio_manager',
  wolverine: 'wolverine',
  flash: 'flash',
  deadpool: 'deadpool',
  cyclops: 'cyclops',
  beast: 'beast',
  cypher: 'cypher',
  codeauditor: 'cypher',
  code_auditor: 'cypher',
  domino: 'domino',
  riskscanner: 'domino',
  risk_scanner: 'domino',
  forge: 'forge',
  opsscanner: 'forge',
  ops_scanner: 'forge',
  iceman: 'ice_man',
  ice_man: 'ice_man',
  externalresearcher: 'ice_man',
  sage: 'sage',
  jean_grey: 'jean_grey',
  jeangrey: 'jean_grey',
  mentor: 'mentor',
  mekka: 'mekka',
  galactus: 'galactus',
  vision_critic: 'vision_critic',
  visioncritic: 'vision_critic',
  vision_moa: 'vision_moa',
  visionmoa: 'vision_moa',
  prometheus: 'prometheus',
};

export function normalizeAgentId(raw) {
  const key = String(raw || '').toLowerCase().replace(/[\s-]+/g, '_');
  return AGENT_ID_MAP[key] || key;
}
