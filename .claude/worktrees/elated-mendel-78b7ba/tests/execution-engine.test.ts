import test from 'node:test';
import assert from 'node:assert/strict';
import { HyperliquidMockConnector } from '../exchanges/hyperliquid/mock-connector';
import { ExecutionEngine } from '../execution-engine/execution-engine';
import { AuditTrail } from '../observability/audit-trail';
import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { RiskEngine } from '../risk-engine/risk-engine';

test('execution engine runs approved paper trade', () => {
  const logger = new Logger();
  const events = new EventPipeline();
  const audit = new AuditTrail();
  const risk = new RiskEngine(logger, events);
  const execution = new ExecutionEngine(risk, new HyperliquidMockConnector(), logger, events, audit);

  const result = execution.submit({
    symbol: 'BTC-USD',
    side: 'buy',
    quantity: 0.1,
    mode: 'paper',
    strategyId: 'paper-ok',
  });

  assert.equal(result.ok, true);
  assert.ok(result.orderId);
  assert.equal(audit.all().length, 2);
});
