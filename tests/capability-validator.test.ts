import test from 'node:test';
import assert from 'node:assert/strict';
import { HYPERLIQUID_MOCK_CONTRACT_V1 } from '../exchanges/hyperliquid/capabilities';
import { HyperliquidCapabilityValidator } from '../exchanges/hyperliquid/capability-validator';

test('capability validator approves compatible connector', () => {
  const validator = new HyperliquidCapabilityValidator();
  const result = validator.validate(
    {
      exchange: 'hyperliquid-mock',
      apiVersion: '1.0.0',
      supportsPaperTrading: true,
      supportsLiveTrading: false,
      supportsWebsocket: true,
      supportsMarketDataFeed: true,
      supportsOrderExecution: true,
    },
    HYPERLIQUID_MOCK_CONTRACT_V1,
  );

  assert.equal(result.valid, true);
  assert.equal(result.reasons.length, 0);
});

test('capability validator rejects live trading enabled', () => {
  const validator = new HyperliquidCapabilityValidator();
  const result = validator.validate(
    {
      exchange: 'hyperliquid-mock',
      apiVersion: '1.0.0',
      supportsPaperTrading: true,
      supportsLiveTrading: true,
      supportsWebsocket: true,
      supportsMarketDataFeed: true,
      supportsOrderExecution: true,
    },
    HYPERLIQUID_MOCK_CONTRACT_V1,
  );

  assert.equal(result.valid, false);
  assert.match(result.reasons.join(' | '), /live trading/i);
});
