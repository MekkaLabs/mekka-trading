#!/usr/bin/env python3
"""
insert_test_signal.py
=====================
Insere um sinal de teste BTC LONG no banco para validar o fluxo TradeNow.

Uso:
    source .venv313/bin/activate
    python insert_test_signal.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Garante que o projeto está no path
sys.path.insert(0, str(Path(__file__).parent))


async def main() -> None:
    from src.persistence.repository import MekkaRepository
    from src.persistence.db import get_session
    from src.persistence.models import SignalRecord

    await MekkaRepository.initialize()

    async with get_session() as session:
        sig = SignalRecord(
            timestamp=datetime.now(timezone.utc),
            symbol="BTC",
            action="LONG",
            confidence=0.87,
            entry_price=104_500.0,   # ajuste ao preço atual se quiser
            stop_loss=101_000.0,     # SL -3.3%
            take_profit=112_000.0,   # TP +7.2%
            size_pct=0.02,           # 2% do capital
            leverage=3,              # 3x
            risk_reward=2.18,
            reasoning=(
                "Breakout confirmado acima da resistência 104k com volume 1.8x acima da média. "
                "RSI 62 (não sobrecomprado), EMA-20 > EMA-50, MACD histograma positivo e crescendo. "
                "Confluência técnica sólida: suporte H4 testado duas vezes, segunda análise "
                "VisionCritic APROVADA. Agentes em consenso: NickFury APROVADO, "
                "Batman APROVADO (drawdown 1.2% < limite 5%). Sinal de teste para validar TradeNow."
            ),
            is_actionable=True,
            fallback=False,
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)

    print("=" * 60)
    print(f"✅ Sinal inserido com sucesso! ID = {sig.id}")
    print(f"   Símbolo  : BTC LONG")
    print(f"   Entrada  : $104,500")
    print(f"   Stop Loss: $101,000 (-3.3%)")
    print(f"   Take Prof: $112,000 (+7.2%)")
    print(f"   Confiança: 87%  |  Leverage: 3x  |  Size: 2%")
    print(f"   RR ratio : 2.18")
    print("=" * 60)
    print()
    print("Agora clique em ⚡ Executar Trade no dashboard.")
    print("O sinal vai aparecer na recomendação com source='agents'")
    print("e o botão 'Confirmar e Executar' ficará habilitado.")


if __name__ == "__main__":
    asyncio.run(main())
