import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { RiskEngine } from './risk-engine';

export type RiskRegime = 'normal' | 'elevated' | 'critical';

export interface RegimeSignal {
  volatilityScore: number;
  liquidityScore: number;
  drawdownScore: number;
}

export class RiskRegimeManager {
  constructor(
    private readonly logger: Logger,
    private readonly events: EventPipeline,
    private readonly riskEngine: RiskEngine,
  ) {}

  evaluate(signal: RegimeSignal, missionId?: string): RiskRegime {
    const max = Math.max(signal.volatilityScore, signal.liquidityScore, signal.drawdownScore);
    const regime: RiskRegime = max >= 0.9 ? 'critical' : max >= 0.7 ? 'elevated' : 'normal';

    this.events.publish('risk.regime.updated', 'risk-regime-manager', { regime, signal }, missionId);

    if (regime === 'critical') {
      this.riskEngine.activateKillSwitch('Critical regime detected by stress signal', missionId);
      this.logger.warn('Critical regime triggered automatic kill switch', { signal });
    }

    return regime;
  }
}
