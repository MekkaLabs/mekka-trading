export interface AgentProfile {
  codename: string;
  role: string;
  mission: string;
}

export const AGENT_REGISTRY: AgentProfile[] = [
  { codename: 'Superman', role: 'Chief Market Overseer', mission: 'Oversee market state transitions and squad alignment.' },
  { codename: 'Batman', role: 'Risk Guardian', mission: 'Enforce hard risk controls and kill switch governance.' },
  { codename: 'Iron Man', role: 'Hyperliquid Execution Engineer', mission: 'Own connector integrity and mock execution flows.' },
  { codename: 'Professor X', role: 'Swarm Coordinator', mission: 'Route autonomous squads and resolve orchestration conflicts.' },
  { codename: 'Doctor Strange', role: 'Macro Probability Analyst', mission: 'Model macro uncertainty and regime likelihood.' },
  { codename: 'Flash', role: 'Momentum Scalper', mission: 'Detect short-term momentum opportunities in paper mode.' },
  { codename: 'Aquaman', role: 'Liquidity Analyst', mission: 'Monitor liquidity pockets and slippage proxies.' },
  { codename: 'Spider-Man', role: 'Anomaly Detector', mission: 'Surface anomalies in market/event streams.' },
  { codename: 'Wolverine', role: 'Recovery Agent', mission: 'Recover from system faults and preserve continuity.' },
  { codename: 'Black Panther', role: 'Onchain Intelligence', mission: 'Track onchain context for strategic weighting.' },
  { codename: 'Nick Fury', role: 'Mission Commander', mission: 'Approve mission envelopes and escalation paths.' },
  { codename: 'Vision', role: 'Predictive Analyst', mission: 'Synthesize predictive features and directional confidence.' },
  { codename: 'Thor', role: 'Volatility Engine', mission: 'Measure and contextualize volatility spikes.' },
  { codename: 'Deadpool', role: 'Chaos Simulator', mission: 'Inject stress scenarios for resilience tests.' },
  { codename: 'Portfolio Manager', role: 'Read-only equity & open-positions snapshot', mission: 'Poll Hyperliquid clearinghouseState read-only and feed Nick Fury equity + Batman open_positions; paper fallback when credentials missing.' },
];
