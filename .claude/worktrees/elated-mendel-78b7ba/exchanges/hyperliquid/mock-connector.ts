import { TradeIntent } from '../../risk-engine/types';
import { ExchangeCapabilities } from './capabilities';

export interface MarketTick {
  symbol: string;
  price: number;
  ts: string;
}

export interface MockExecutionResult {
  exchange: 'hyperliquid-mock';
  status: 'accepted';
  orderId: string;
  intent: TradeIntent;
  executedAt: string;
}

export class HyperliquidMockConnector {
  connectWebsocket(): { status: 'connected'; endpoint: string } {
    return { status: 'connected', endpoint: 'wss://mock.hyperliquid.local/ws' };
  }

  handshakeCapabilities(): ExchangeCapabilities {
    return {
      exchange: 'hyperliquid-mock',
      apiVersion: '1.0.0',
      supportsPaperTrading: true,
      supportsLiveTrading: false,
      supportsWebsocket: true,
      supportsMarketDataFeed: true,
      supportsOrderExecution: true,
    };
  }

  getMarketFeed(symbol: string): MarketTick {
    return {
      symbol,
      price: 100 + Math.random() * 10,
      ts: new Date().toISOString(),
    };
  }

  executeOrder(intent: TradeIntent): MockExecutionResult {
    return {
      exchange: 'hyperliquid-mock',
      status: 'accepted',
      orderId: `mock-${Date.now()}`,
      intent,
      executedAt: new Date().toISOString(),
    };
  }
}
