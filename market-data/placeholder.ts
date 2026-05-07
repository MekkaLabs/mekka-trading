export interface MarketDataSnapshot {
  symbol: string;
  bid: number;
  ask: number;
  timestamp: string;
}

export const MARKET_DATA_MODE = 'mock-only';
