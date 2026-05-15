export interface RiskPolicy {
  paperOnly: boolean;
  maxOrderQuantity: number;
  maxOrderNotionalUsd: number;
  maxSymbolPosition: number;
  maxDailyLossUsd: number;
}

export const DEFAULT_RISK_POLICY: RiskPolicy = {
  paperOnly: true,
  maxOrderQuantity: 5,
  maxOrderNotionalUsd: 50_000,
  maxSymbolPosition: 10,
  maxDailyLossUsd: 2_500,
};
