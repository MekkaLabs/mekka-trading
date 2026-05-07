import { SQUADS, Squad } from '../squads/squads';

export interface RouteDecision {
  mission: string;
  squads: Squad[];
}

export class SquadRouter {
  route(objective: string): RouteDecision {
    const lower = objective.toLowerCase();
    const selected: Squad[] = [];

    if (lower.includes('risk') || lower.includes('drawdown')) {
      selected.push(...SQUADS.filter((s) => s.name === 'alpha-risk-command'));
    }

    if (lower.includes('execution') || lower.includes('hyperliquid')) {
      selected.push(...SQUADS.filter((s) => s.name === 'hyperliquid-mock-ops'));
    }

    selected.push(...SQUADS.filter((s) => s.name === 'market-intel-lab'));

    const dedup = Array.from(new Map(selected.map((s) => [s.name, s])).values());
    return { mission: objective, squads: dedup };
  }
}
