"""
src/services/consensus_weighter.py
=====================================
ConsensusWeighter — Story 241 (Milestone 39: Multiagent Debate).

Agrega votos de múltiplos agentes ponderando por confiança declarada e
rodada do debate. Votos de rodadas posteriores têm peso ligeiramente maior
(agentes puderam revisar posição após ver os votos anteriores).

Uso::

    weighter = ConsensusWeighter()
    verdict  = weighter.aggregate(votes, rounds_run=2)
    print(verdict.consensus_action, verdict.consensus_confidence)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from src.services.debate_moderator import DebateVerdict, DebateVote


class ConsensusWeighter:
    """
    Agrega votos ponderados por confiança e rodada.

    Fórmula de peso por voto:
        weight = confidence * round_multiplier
        round_multiplier = 1.0 + (round_num - 1) * 0.1
        (rodada 1 → 1.0×, rodada 2 → 1.1×, rodada 3 → 1.2×)

    O consenso é a ação com maior soma de pesos normalizados.
    """

    ROUND_MULTIPLIER_STEP = 0.10

    def aggregate(
        self,
        votes: List[DebateVote],
        rounds_run: int = 1,
    ) -> DebateVerdict:
        """
        Agrega votos e retorna DebateVerdict com ação e confiança do consenso.
        """
        if not votes:
            return DebateVerdict(
                consensus_action="HOLD",
                consensus_confidence=0.0,
                total_votes=0,
                rounds_run=rounds_run,
                notes=["Nenhum voto recebido"],
            )

        # Somar pesos por ação
        action_weights: Dict[str, float] = defaultdict(float)
        total_weight = 0.0

        for vote in votes:
            multiplier = 1.0 + (vote.round_num - 1) * self.ROUND_MULTIPLIER_STEP
            weight     = max(0.0, vote.confidence) * multiplier
            action_weights[vote.action] += weight
            total_weight += weight

        if total_weight == 0:
            return DebateVerdict(
                consensus_action="HOLD",
                consensus_confidence=0.0,
                total_votes=len(votes),
                rounds_run=rounds_run,
                votes=votes,
                notes=["Todos os votos têm confiança zero"],
            )

        # Normalizar
        action_fractions = {
            action: w / total_weight
            for action, w in action_weights.items()
        }

        # Ação vencedora
        consensus_action = max(action_fractions, key=action_fractions.__getitem__)
        consensus_conf   = action_fractions[consensus_action]

        # Agentes dissidentes (votaram diferente do consenso na última rodada)
        last_round = max(v.round_num for v in votes)
        dissent = [
            v.agent for v in votes
            if v.round_num == last_round and v.action != consensus_action
        ]

        notes = []
        if len(action_fractions) == 3:
            notes.append("Agentes divididos entre LONG, SHORT e HOLD — baixa convicção")
        elif consensus_conf < 0.50:
            notes.append(f"Consenso fraco ({consensus_conf:.0%}) — Vision deve ponderar com cautela")

        return DebateVerdict(
            consensus_action=consensus_action,
            consensus_confidence=round(consensus_conf, 4),
            total_votes=len(votes),
            rounds_run=rounds_run,
            votes=votes,
            dissent_agents=dissent,
            notes=notes,
        )

    def summary_table(self, votes: List[DebateVote]) -> List[dict]:
        """Tabela resumida de votos para logging/dashboard."""
        return [
            {
                "agent":      v.agent,
                "action":     v.action,
                "confidence": round(v.confidence, 3),
                "round":      v.round_num,
                "reasoning":  v.reasoning[:80] + "…" if len(v.reasoning) > 80 else v.reasoning,
            }
            for v in sorted(votes, key=lambda v: (v.round_num, v.agent))
        ]
