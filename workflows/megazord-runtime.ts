import path from 'node:path';
import { HYPERLIQUID_MOCK_CONTRACT_V1 } from '../exchanges/hyperliquid/capabilities';
import { HyperliquidCapabilityValidator } from '../exchanges/hyperliquid/capability-validator';
import { HyperliquidMockConnector } from '../exchanges/hyperliquid/mock-connector';
import { ExecutionEngine } from '../execution-engine/execution-engine';
import { SCENARIO_PACKS, ScenarioName } from '../market-data/scenario-pack';
import { AuditTrail } from '../observability/audit-trail';
import { EventPipeline } from '../observability/event-pipeline';
import { Logger } from '../observability/logger';
import { MissionReporter } from '../observability/reports/mission-reporter';
import { AppendOnlyStore } from '../observability/store/append-only-store';
import { PositionBook } from '../risk-engine/position-book';
import { RiskEngine } from '../risk-engine/risk-engine';
import { RiskRegime, RiskRegimeManager } from '../risk-engine/regime-manager';
import { MockStrategyEngine } from '../strategy-engine/mock-strategy';
import { MissionPlanner } from './mission-planner';
import { SquadRouter } from './squad-router';

export interface RuntimeReport {
  missionId: string;
  objective: string;
  routedSquads: string[];
  accepted: number;
  blocked: number;
  events: number;
  audits: number;
  riskRegime: RiskRegime;
  scenario: ScenarioName;
  capabilityValidation: {
    valid: boolean;
    reasons: string[];
  };
}

export interface MissionReplay {
  missionId: string;
  events: number;
  audits: number;
}

export interface MissionIntegrity {
  missionId: string;
  events: { valid: boolean; checked: number; reason?: string };
  audits: { valid: boolean; checked: number; reason?: string };
}

export interface RuntimeOptions {
  memoryBaseDir?: string;
}

export class MegazordRuntime {
  private readonly logger = new Logger();
  private readonly store: AppendOnlyStore;
  private readonly reporter: MissionReporter;
  private readonly events: EventPipeline;
  private readonly audit: AuditTrail;
  private readonly positions = new PositionBook();
  private readonly risk: RiskEngine;
  private readonly regime: RiskRegimeManager;
  private readonly connector = new HyperliquidMockConnector();
  private readonly capabilityValidator = new HyperliquidCapabilityValidator();
  private readonly execution: ExecutionEngine;
  private readonly planner = new MissionPlanner();
  private readonly router = new SquadRouter();
  private readonly strategy = new MockStrategyEngine();

  constructor(options: RuntimeOptions = {}) {
    const memoryBaseDir = options.memoryBaseDir ?? path.join(process.cwd(), 'memory');
    const auditLogDir = path.join(memoryBaseDir, 'audit-log');
    const reportsDir = path.join(memoryBaseDir, 'reports');

    this.store = new AppendOnlyStore(auditLogDir);
    this.reporter = new MissionReporter(this.store, reportsDir);
    this.events = new EventPipeline(this.store);
    this.audit = new AuditTrail(this.store);
    this.risk = new RiskEngine(this.logger, this.events, undefined, this.positions);
    this.regime = new RiskRegimeManager(this.logger, this.events, this.risk);
    this.execution = new ExecutionEngine(this.risk, this.connector, this.logger, this.events, this.audit);
  }

  run(objective: string, symbols: string[], scenario: ScenarioName = 'normal'): RuntimeReport {
    const plan = this.planner.create(objective, symbols);
    const routing = this.router.route(objective);
    const scenarioPack = SCENARIO_PACKS[scenario];

    this.logger.info('Workflow stage: INPUT', { objective, symbols, scenario });
    this.logger.info('Workflow stage: ANALYSIS', { missionId: plan.missionId });
    this.logger.info('Workflow stage: DECOMPOSITION', { stages: plan.workflowStages });

    const capabilities = this.connector.handshakeCapabilities();
    const capabilityValidation = this.capabilityValidator.validate(capabilities, HYPERLIQUID_MOCK_CONTRACT_V1);
    this.events.publish(
      'exchange.capabilities.validated',
      'megazord-runtime',
      { valid: capabilityValidation.valid, reasons: capabilityValidation.reasons },
      plan.missionId,
    );

    if (!capabilityValidation.valid) {
      this.risk.activateKillSwitch('Exchange capability validation failed', plan.missionId);
      this.logger.error('Capability validation failed. Mission blocked.', {
        missionId: plan.missionId,
        reasons: capabilityValidation.reasons,
      });

      return {
        missionId: plan.missionId,
        objective,
        routedSquads: routing.squads.map((s) => s.name),
        accepted: 0,
        blocked: symbols.length,
        events: this.events.list().length,
        audits: this.audit.all().length,
        riskRegime: 'critical',
        scenario,
        capabilityValidation,
      };
    }

    const riskRegime = this.regime.evaluate(scenarioPack.signal, plan.missionId);
    this.risk.registerLoss(scenarioPack.simulatedLossUsd, plan.missionId);

    this.logger.info('Workflow stage: ROUTING', {
      squads: routing.squads.map((s) => s.name),
      websocket: this.connector.connectWebsocket(),
      riskRegime,
    });

    const intents = this.strategy.buildIntents({ cycleId: plan.missionId, symbols: plan.symbols });
    let accepted = 0;
    let blocked = 0;

    for (const intent of intents) {
      const outcome = this.execution.submit(intent);
      if (outcome.ok) accepted += 1;
      else blocked += 1;
    }

    this.logger.info('Workflow stage: EXECUTION', { accepted, blocked });
    this.logger.info('Workflow stage: VALIDATION', { events: this.events.list().length, audits: this.audit.all().length });

    const integrity = this.verifyMissionIntegrity(plan.missionId);
    if (!integrity.events.valid || !integrity.audits.valid) {
      this.events.publish(
        'observability.integrity.alert',
        'megazord-runtime',
        {
          missionId: plan.missionId,
          events: integrity.events,
          audits: integrity.audits,
        },
        plan.missionId,
      );
      this.logger.error('Integrity alert detected in mission streams', {
        missionId: plan.missionId,
        events: integrity.events,
        audits: integrity.audits,
      });
    }

    this.logger.info('Workflow stage: REFLECTION', {
      note: 'Megazord cycle completed with strict paper-only guardrails.',
      riskRegime,
      scenario,
    });
    this.logger.info('Workflow stage: OUTPUT', { status: 'megazord-cycle-finished' });

    return {
      missionId: plan.missionId,
      objective,
      routedSquads: routing.squads.map((s) => s.name),
      accepted,
      blocked,
      events: this.events.list().length,
      audits: this.audit.all().length,
      riskRegime,
      scenario,
      capabilityValidation,
    };
  }

  replayMission(missionId: string): MissionReplay {
    const events = this.store.replay('events', missionId);
    const audits = this.store.replay('audits', missionId);
    return {
      missionId,
      events: events.length,
      audits: audits.length,
    };
  }

  verifyMissionIntegrity(missionId: string): MissionIntegrity {
    return {
      missionId,
      events: this.store.verifyIntegrity('events', missionId),
      audits: this.store.verifyIntegrity('audits', missionId),
    };
  }

  exportMissionReport(missionId: string): string {
    return this.reporter.exportReport(missionId);
  }
}
