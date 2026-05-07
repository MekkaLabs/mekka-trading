import { TradeIntent } from '../risk-engine/types';

export interface StrategyContext {
  cycleId: string;
  symbols: string[];
}

export class MockStrategyEngine {
  buildIntents(context: StrategyContext): TradeIntent[] {
    return context.symbols.map((symbol, index) => ({
      symbol,
      side: index % 2 === 0 ? 'buy' : 'sell',
      quantity: 0.25,
      mode: 'paper',
      strategyId: `megazord-${context.cycleId}`,
      price: 100 + index,
    }));
  }
}
