import { RegimeSignal } from '../risk-engine/regime-manager';

export type ScenarioName = 'normal' | 'volatility-spike' | 'liquidity-shock' | 'drawdown-event';

export interface ScenarioPack {
  name: ScenarioName;
  signal: RegimeSignal;
  simulatedLossUsd: number;
}

export const SCENARIO_PACKS: Record<ScenarioName, ScenarioPack> = {
  normal: {
    name: 'normal',
    signal: { volatilityScore: 0.35, liquidityScore: 0.3, drawdownScore: 0.2 },
    simulatedLossUsd: 50,
  },
  'volatility-spike': {
    name: 'volatility-spike',
    signal: { volatilityScore: 0.85, liquidityScore: 0.55, drawdownScore: 0.6 },
    simulatedLossUsd: 900,
  },
  'liquidity-shock': {
    name: 'liquidity-shock',
    signal: { volatilityScore: 0.6, liquidityScore: 0.92, drawdownScore: 0.65 },
    simulatedLossUsd: 1200,
  },
  'drawdown-event': {
    name: 'drawdown-event',
    signal: { volatilityScore: 0.65, liquidityScore: 0.7, drawdownScore: 0.95 },
    simulatedLossUsd: 2600,
  },
};
