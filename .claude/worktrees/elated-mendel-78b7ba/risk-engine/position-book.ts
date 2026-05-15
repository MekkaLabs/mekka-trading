export class PositionBook {
  private readonly positions = new Map<string, number>();
  private realizedPnlUsd = 0;

  getPosition(symbol: string): number {
    return this.positions.get(symbol) ?? 0;
  }

  applyFill(symbol: string, side: 'buy' | 'sell', quantity: number): number {
    const current = this.getPosition(symbol);
    const signedQty = side === 'buy' ? quantity : -quantity;
    const next = current + signedQty;
    this.positions.set(symbol, next);
    return next;
  }

  addRealizedLoss(lossUsd: number): number {
    this.realizedPnlUsd -= Math.abs(lossUsd);
    return this.realizedPnlUsd;
  }

  getRealizedPnlUsd(): number {
    return this.realizedPnlUsd;
  }
}
