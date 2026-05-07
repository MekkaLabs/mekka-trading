export type TradeSide = 'buy' | 'sell';

export interface TradeIntent {
  symbol: string;
  side: TradeSide;
  quantity: number;
  price?: number;
  mode: 'paper' | 'live';
  strategyId: string;
}

export interface RiskDecision {
  approved: boolean;
  reason: string;
  killSwitchActive: boolean;
}
