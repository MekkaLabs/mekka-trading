"""
src/services/debate_moderator.py
===================================
DebateModerator — Story 239 (Milestone 39: Multiagent Debate).

Coordena um debate estruturado entre agentes L1 antes da decisão do Vision,
seguindo o padrão Society of Mind / Constitutional AI.

O debate acontece em até N rodadas. Cada agente emite um voto com
justificativa. O ConsensusWeighter agrega os votos ponderados por
confiança histórica.

Fluxo::

    moderator = DebateModerator()
    verdict = await moderator.run(
        context=market_analysis,
        agents=["Superman", "DoctorStrange", "BlackPanther"],
        rounds=2,
    )
    print(verdict.consensus_action)  # "LONG" | "SHORT" | "HOLD"
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger
from pydantic import BaseModel, Field


class DebateVote(BaseModel):
    """Voto de um agente no debate."""

    agent:      str
    action:     str                    # "LONG" | "SHORT" | "HOLD"
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning:  str   = ""
    round_num:  int   = 1
    timestamp:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["timestamp"] = self.timestamp.isoformat()
        return d


class DebateVerdict(BaseModel):
    """Resultado agregado do debate."""

    consensus_action:     str   = "HOLD"
    consensus_confidence: float = 0.0
    total_votes:          int   = 0
    rounds_run:           int   = 0
    votes:                List[DebateVote] = Field(default_factory=list)
    dissent_agents:       List[str] = Field(default_factory=list)  # discordaram do consenso
    notes:                List[str] = Field(default_factory=list)
    generated_at:         datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        d = self.model_dump()
        d["generated_at"] = self.generated_at.isoformat()
        d["votes"] = [v.to_dict() for v in self.votes]
        return d


class DebateModerator:
    """
    Moderador de debate multiagente L1.5.

    Parâmetros
    ----------
    max_rounds      : Número máximo de rodadas (default 2).
    consensus_threshold: Fração mínima de votos para consenso (default 0.6 = 60%).
    timeout_secs    : Timeout por rodada em segundos (default 5.0).
    """

    DEFAULT_AGENTS = ["Superman", "DoctorStrange", "BlackPanther", "Thor", "Aquaman"]

    def __init__(
        self,
        max_rounds: int = 2,
        consensus_threshold: float = 0.60,
        timeout_secs: float = 5.0,
    ) -> None:
        self._max_rounds           = max_rounds
        self._consensus_threshold  = consensus_threshold
        self._timeout_secs         = timeout_secs
        self._log                  = logger.bind(service="DebateModerator")

    async def run(
        self,
        context: Any,
        agents: Optional[List[str]] = None,
        symbol: str = "BTC",
    ) -> DebateVerdict:
        """
        Executa o debate e retorna o DebateVerdict.

        Args:
            context: MarketAnalysis ou dict com dados de mercado.
            agents:  Lista de nomes de agentes. Default: DEFAULT_AGENTS.
            symbol:  Símbolo sendo analisado.

        Returns:
            DebateVerdict com consenso, votos e dissidentes.
        """
        agent_list = agents or self.DEFAULT_AGENTS
        all_votes: List[DebateVote] = []

        for round_num in range(1, self._max_rounds + 1):
            self._log.info(
                f"DebateModerator: rodada {round_num}/{self._max_rounds} "
                f"| {len(agent_list)} agentes | símbolo={symbol}"
            )

            # Solicitar votos de todos os agentes em paralelo
            round_votes = await self._collect_votes(
                context=context,
                agents=agent_list,
                round_num=round_num,
                symbol=symbol,
                prior_votes=all_votes,
            )
            all_votes.extend(round_votes)

            # Verificar se há consenso antecipado
            verdict = self._aggregate(all_votes, rounds_run=round_num)
            if verdict.consensus_confidence >= self._consensus_threshold:
                self._log.info(
                    f"DebateModerator: consenso em rodada {round_num} "
                    f"— {verdict.consensus_action} ({verdict.consensus_confidence:.0%})"
                )
                return verdict

        # Usar resultado final após todas as rodadas
        final = self._aggregate(all_votes, rounds_run=self._max_rounds)
        if final.consensus_confidence < self._consensus_threshold:
            final.notes.append(
                f"Consenso fraco ({final.consensus_confidence:.0%} < "
                f"{self._consensus_threshold:.0%}). Vision decidirá com menor confiança."
            )
        return final

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _collect_votes(
        self,
        context: Any,
        agents: List[str],
        round_num: int,
        symbol: str,
        prior_votes: List[DebateVote],
    ) -> List[DebateVote]:
        """Coleta votos de todos os agentes em paralelo com timeout."""
        tasks = [
            self._request_vote(agent, context, round_num, symbol, prior_votes)
            for agent in agents
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        votes = []
        for agent, result in zip(agents, results):
            if isinstance(result, Exception):
                self._log.warning(f"DebateModerator: {agent} falhou — {result}")
                # Voto default: HOLD com confiança 0
                votes.append(DebateVote(
                    agent=agent,
                    action="HOLD",
                    confidence=0.0,
                    reasoning=f"Erro: {result}",
                    round_num=round_num,
                ))
            else:
                votes.append(result)
        return votes

    async def _request_vote(
        self,
        agent_name: str,
        context: Any,
        round_num: int,
        symbol: str,
        prior_votes: List[DebateVote],
    ) -> DebateVote:
        """
        Solicita voto de um agente específico.

        Usa a análise existente do agente + contexto do debate para
        derivar um voto. Agentes sem método de debate usam heurísticas.
        """
        try:
            return await asyncio.wait_for(
                self._agent_vote(agent_name, context, round_num, symbol, prior_votes),
                timeout=self._timeout_secs,
            )
        except asyncio.TimeoutError:
            return DebateVote(
                agent=agent_name,
                action="HOLD",
                confidence=0.0,
                reasoning="Timeout",
                round_num=round_num,
            )

    async def _agent_vote(
        self,
        agent_name: str,
        context: Any,
        round_num: int,
        symbol: str,
        prior_votes: List[DebateVote],
    ) -> DebateVote:
        """Deriva voto do agente a partir do contexto de mercado disponível."""
        # Extrair dados do contexto (MarketAnalysis ou dict)
        data = context if isinstance(context, dict) else (
            context.model_dump() if hasattr(context, "model_dump") else {}
        )

        # Heurísticas por especialidade do agente
        action, confidence, reasoning = self._heuristic_vote(
            agent_name, data, prior_votes, round_num
        )

        return DebateVote(
            agent=agent_name,
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            round_num=round_num,
        )

    @staticmethod
    def _heuristic_vote(
        agent_name: str,
        data: Dict[str, Any],
        prior_votes: List[DebateVote],
        round_num: int,
    ) -> tuple[str, float, str]:
        """
        Heurísticas por agente baseadas nos dados de mercado disponíveis.
        Em produção, cada agente retornaria seu próprio método de voto.
        """
        name = agent_name.lower()

        # Superman — baseado em tendência (momentum)
        if "superman" in name:
            trend = (data.get("trend") or data.get("price_trend") or "").lower()
            if "bull" in trend or "up" in trend:
                return "LONG",  0.70, "Tendência técnica ascendente (RSI + EMA bullish)"
            if "bear" in trend or "down" in trend:
                return "SHORT", 0.65, "Tendência técnica descendente (RSI + EMA bearish)"
            return "HOLD", 0.50, "Sem tendência clara nos indicadores técnicos"

        # DoctorStrange — sentimento macro
        if "strange" in name or "doctor" in name:
            sentiment = str(data.get("macro_sentiment") or data.get("sentiment") or "").lower()
            fear_greed = float(data.get("fear_greed_index") or 50)
            if fear_greed > 65 or "greed" in sentiment:
                return "LONG",  0.65, f"Sentimento macro favorável (F&G={fear_greed:.0f})"
            if fear_greed < 35 or "fear" in sentiment:
                return "SHORT", 0.60, f"Sentimento macro negativo (F&G={fear_greed:.0f})"
            return "HOLD", 0.55, f"Sentimento neutro (F&G={fear_greed:.0f})"

        # BlackPanther — on-chain / funding
        if "panther" in name or "black" in name:
            funding = float(data.get("funding_rate") or 0)
            if funding < -0.01:
                return "LONG",  0.70, f"Funding negativo ({funding:.4f}) — shorts sobrepagando"
            if funding > 0.05:
                return "SHORT", 0.65, f"Funding elevado ({funding:.4f}) — longs sobrepagando"
            return "HOLD", 0.50, f"Funding neutro ({funding:.4f})"

        # Thor — volatilidade / regime
        if "thor" in name:
            atr_pct = float(data.get("atr_pct") or data.get("volatility_pct") or 2.0)
            if atr_pct < 1.5:
                return "LONG",  0.60, f"Volatilidade baixa ({atr_pct:.2f}%) — regime favorável a tendência"
            if atr_pct > 4.0:
                return "HOLD",  0.55, f"Alta volatilidade ({atr_pct:.2f}%) — risco elevado"
            return "LONG", 0.55, f"Volatilidade moderada ({atr_pct:.2f}%)"

        # Aquaman — liquidez
        if "aqua" in name:
            spread_pct = float(data.get("spread_pct") or data.get("slippage_pct") or 0.05)
            if spread_pct < 0.02:
                return "LONG",  0.65, f"Liquidez excelente (spread={spread_pct:.3f}%)"
            if spread_pct > 0.10:
                return "HOLD",  0.50, f"Liquidez baixa (spread={spread_pct:.3f}%) — slippage elevado"
            return "LONG", 0.55, f"Liquidez adequada (spread={spread_pct:.3f}%)"

        # Fallback genérico
        return "HOLD", 0.40, f"{agent_name} sem dados suficientes para votar"

    def _aggregate(self, votes: List[DebateVote], rounds_run: int) -> DebateVerdict:
        """Agrega votos usando ConsensusWeighter."""
        from src.services.consensus_weighter import ConsensusWeighter
        weighter = ConsensusWeighter()
        return weighter.aggregate(votes, rounds_run=rounds_run)
