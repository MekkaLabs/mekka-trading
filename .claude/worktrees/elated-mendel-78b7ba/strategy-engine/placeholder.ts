export interface StrategySignal {
  strategyId: string;
  symbol: string;
  action: 'buy' | 'sell' | 'hold';
  confidence: number;
}

export const STRATEGY_ENGINE_STATUS = 'foundation-ready';
