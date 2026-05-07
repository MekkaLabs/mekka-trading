export interface ExchangeCapabilities {
  exchange: 'hyperliquid-mock';
  apiVersion: string;
  supportsPaperTrading: boolean;
  supportsLiveTrading: boolean;
  supportsWebsocket: boolean;
  supportsMarketDataFeed: boolean;
  supportsOrderExecution: boolean;
}

export interface CapabilityContract {
  minApiVersion: string;
  requirePaperTrading: boolean;
  requireWebsocket: boolean;
  requireMarketDataFeed: boolean;
  requireOrderExecution: boolean;
  forbidLiveTrading: boolean;
}

export const HYPERLIQUID_MOCK_CONTRACT_V1: CapabilityContract = {
  minApiVersion: '1.0.0',
  requirePaperTrading: true,
  requireWebsocket: true,
  requireMarketDataFeed: true,
  requireOrderExecution: true,
  forbidLiveTrading: true,
};
