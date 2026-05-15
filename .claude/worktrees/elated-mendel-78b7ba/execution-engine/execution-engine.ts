import { HyperliquidMockConnector } from '../exchanges/hyperliquid/mock-connector';
import { AuditTrail } from '../observability/audit-trail';
import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { RiskEngine } from '../risk-engine/risk-engine';
import { TradeIntent } from '../risk-engine/types';

export interface ExecutionResult {
  ok: boolean;
  reason?: string;
  orderId?: string;
}

export class ExecutionEngine {
  constructor(
    private readonly riskEngine: RiskEngine,
    private readonly connector: HyperliquidMockConnector,
    private readonly logger: Logger,
    private readonly events: EventPipeline,
    private readonly audit: AuditTrail,
  ) {}

  submit(intent: TradeIntent): ExecutionResult {
    const decision = this.riskEngine.validate(intent);
    const missionId = intent.strategyId.replace('megazord-', '');

    this.audit.add(
      'trade',
      'risk-engine',
      {
        strategyId: intent.strategyId,
        symbol: intent.symbol,
        approved: decision.approved,
        reason: decision.reason,
      },
      missionId,
    );

    if (!decision.approved) {
      this.logger.warn('Trade blocked by risk engine', { intent, decision });
      this.events.publish(
        'execution.blocked',
        'execution-engine',
        {
          symbol: intent.symbol,
          reason: decision.reason,
        },
        missionId,
      );
      return { ok: false, reason: decision.reason };
    }

    const result = this.connector.executeOrder(intent);
    this.riskEngine.registerExecution(intent);
    this.audit.add(
      'execution',
      'execution-engine',
      {
        orderId: result.orderId,
        symbol: intent.symbol,
        mode: intent.mode,
        exchange: result.exchange,
      },
      missionId,
    );
    this.events.publish('execution.paper_order.accepted', 'execution-engine', result as unknown as Record<string, unknown>, missionId);
    this.logger.info('Paper trade executed in mock mode', { orderId: result.orderId });

    return { ok: true, orderId: result.orderId };
  }
}
