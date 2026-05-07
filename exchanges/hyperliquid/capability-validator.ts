import { CapabilityContract, ExchangeCapabilities } from './capabilities';

export interface CapabilityValidation {
  valid: boolean;
  reasons: string[];
}

function compareVersion(a: string, b: string): number {
  const pa = a.split('.').map((v) => Number(v));
  const pb = b.split('.').map((v) => Number(v));
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i += 1) {
    const da = pa[i] ?? 0;
    const db = pb[i] ?? 0;
    if (da > db) return 1;
    if (da < db) return -1;
  }
  return 0;
}

export class HyperliquidCapabilityValidator {
  validate(capabilities: ExchangeCapabilities, contract: CapabilityContract): CapabilityValidation {
    const reasons: string[] = [];

    if (compareVersion(capabilities.apiVersion, contract.minApiVersion) < 0) {
      reasons.push(`API version too old: got ${capabilities.apiVersion}, requires >= ${contract.minApiVersion}`);
    }

    if (contract.requirePaperTrading && !capabilities.supportsPaperTrading) {
      reasons.push('Paper trading support is required');
    }

    if (contract.forbidLiveTrading && capabilities.supportsLiveTrading) {
      reasons.push('Live trading must be disabled in this stage');
    }

    if (contract.requireWebsocket && !capabilities.supportsWebsocket) {
      reasons.push('Websocket support is required');
    }

    if (contract.requireMarketDataFeed && !capabilities.supportsMarketDataFeed) {
      reasons.push('Market data feed support is required');
    }

    if (contract.requireOrderExecution && !capabilities.supportsOrderExecution) {
      reasons.push('Order execution capability is required');
    }

    return {
      valid: reasons.length === 0,
      reasons,
    };
  }
}
