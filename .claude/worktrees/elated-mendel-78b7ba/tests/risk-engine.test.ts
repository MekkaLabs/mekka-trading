import test from 'node:test';
import assert from 'node:assert/strict';
import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { RiskEngine } from '../risk-engine/risk-engine';

test('risk engine blocks live trading', () => {
  const risk = new RiskEngine(new Logger(), new EventPipeline());
  const result = risk.validate({
    symbol: 'ETH-USD',
    side: 'buy',
    quantity: 1,
    mode: 'live',
    strategyId: 't1',
  });

  assert.equal(result.approved, false);
  assert.match(result.reason, /paper trading/i);
});

test('risk engine kill switch blocks all intents', () => {
  const risk = new RiskEngine(new Logger(), new EventPipeline());
  risk.activateKillSwitch('manual-stop');
  const result = risk.validate({
    symbol: 'ETH-USD',
    side: 'sell',
    quantity: 1,
    mode: 'paper',
    strategyId: 't2',
  });

  assert.equal(result.approved, false);
  assert.match(result.reason, /kill switch/i);
});

test('risk engine blocks order above quantity limit', () => {
  const risk = new RiskEngine(new Logger(), new EventPipeline());
  const result = risk.validate({
    symbol: 'BTC-USD',
    side: 'buy',
    quantity: 99,
    mode: 'paper',
    strategyId: 't3',
    price: 100,
  });

  assert.equal(result.approved, false);
  assert.match(result.reason, /quantity/i);
});
