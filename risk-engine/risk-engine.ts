import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { RiskPolicy, DEFAULT_RISK_POLICY } from './policy';
import { PositionBook } from './position-book';
import { TradeIntent, RiskDecision } from './types';

export class RiskEngine {
  private killSwitchActive = false;

  constructor(
    private readonly logger: Logger,
    private readonly events: EventPipeline,
    private readonly policy: RiskPolicy = DEFAULT_RISK_POLICY,
    private readonly positions: PositionBook = new PositionBook(),
  ) {}

  activateKillSwitch(reason: string, missionId?: string): void {
    this.killSwitchActive = true;
    this.logger.warn('Kill switch activated', { reason });
    this.events.publish('risk.kill_switch.activated', 'risk-engine', { reason }, missionId);
  }

  deactivateKillSwitch(missionId?: string): void {
    this.killSwitchActive = false;
    this.logger.info('Kill switch deactivated');
    this.events.publish('risk.kill_switch.deactivated', 'risk-engine', {}, missionId);
  }

  registerExecution(intent: TradeIntent): void {
    const nextPosition = this.positions.applyFill(intent.symbol, intent.side, intent.quantity);
    const missionId = intent.strategyId.replace('megazord-', '');
    this.events.publish(
      'risk.position.updated',
      'risk-engine',
      {
        symbol: intent.symbol,
        nextPosition,
      },
      missionId,
    );
  }

  registerLoss(lossUsd: number, missionId?: string): void {
    const pnl = this.positions.addRealizedLoss(lossUsd);
    this.events.publish('risk.pnl.updated', 'risk-engine', { realizedPnlUsd: pnl }, missionId);
    if (Math.abs(pnl) >= this.policy.maxDailyLossUsd) {
      this.activateKillSwitch('Daily loss threshold reached', missionId);
    }
  }

  validate(intent: TradeIntent): RiskDecision {
    if (this.killSwitchActive) {
      return { approved: false, reason: 'Kill switch active', killSwitchActive: true };
    }

    if (this.policy.paperOnly && intent.mode !== 'paper') {
      return { approved: false, reason: 'Only paper trading is allowed', killSwitchActive: false };
    }

    if (!intent.symbol || intent.quantity <= 0) {
      return { approved: false, reason: 'Invalid trade intent payload', killSwitchActive: false };
    }

    if (intent.quantity > this.policy.maxOrderQuantity) {
      return { approved: false, reason: 'Order quantity above allowed max', killSwitchActive: false };
    }

    const refPrice = intent.price ?? 0;
    if (refPrice > 0 && refPrice * intent.quantity > this.policy.maxOrderNotionalUsd) {
      return { approved: false, reason: 'Order notional above allowed max', killSwitchActive: false };
    }

    const currentPosition = this.positions.getPosition(intent.symbol);
    const projected = currentPosition + (intent.side === 'buy' ? intent.quantity : -intent.quantity);
    if (Math.abs(projected) > this.policy.maxSymbolPosition) {
      return { approved: false, reason: 'Projected symbol position above limit', killSwitchActive: false };
    }

    return { approved: true, reason: 'Validated for paper execution', killSwitchActive: false };
  }
}
