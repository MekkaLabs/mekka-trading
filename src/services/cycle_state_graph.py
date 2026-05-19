"""
src/services/cycle_state_graph.py
==================================
Story 208 — CycleStateGraph: grafo de estado tipado para o pipeline Mekka,
inspirado no LangGraph StateGraph + CompiledGraph.

Inspirado no padrão LangGraph StateGraph:
(langchain-ai/langgraph, github.com/langchain-ai/langgraph):
  "LangGraph models agent workflows as directed graphs where:
   - Each node is a callable that receives and returns state
   - Edges define the flow between nodes
   - State is a typed dict that accumulates across transitions
   - StateGraph.compile() returns a CompiledGraph that can be invoked
   Example:
     class State(TypedDict):
         messages: list
         signal: str
     graph = StateGraph(State)
     graph.add_node('vision', vision_node)
     graph.add_edge('vision', 'batman')
     compiled = graph.compile()
     result = compiled.invoke({'messages': [], 'signal': ''})"

No Mekka:
  CycleState é o TypedDict que flui por todos os nós do pipeline:
  symbol, cycle_id, market_data, signal, risk_report, execution_result,
  errors, metadata — cada nó lê e escreve no estado compartilhado.

  CycleStateGraph registra nós (vision_node, batman_node, ironman_node),
  arestas fixas e condicionais, compila em CycleCompiledGraph e expõe
  invoke(state) que executa o grafo de estado de ponta a ponta.

Arquitetura
-----------
  CycleState           — TypedDict completo do pipeline
  CycleGraphNode       — wrapper de um nó (name + fn + metadata)
  CycleStateGraph
    ├── add_node(name, fn)
    ├── add_edge(src, dst)
    ├── set_entry_point(name)
    ├── set_finish_point(name)
    └── compile() → CycleCompiledGraph
  CycleCompiledGraph
    ├── invoke(state) → CycleState          (síncrono)
    └── stream(state) → Iterator[CycleState] (step a step)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from loguru import logger


# ---------------------------------------------------------------------------
# CycleState — TypedDict-like do pipeline Mekka
# ---------------------------------------------------------------------------

class CycleState(dict):
    """
    Estado tipado que flui por todos os nós do pipeline.

    É um dict normal com acesso por chave — compatível com qualquer função
    existente que já receba/retorne dicts. A tipagem é soft (sem mypy aqui)
    mas a documentação abaixo serve como contrato:

    Campos principais:
      symbol        str   — ativo sendo analisado ("BTC", "ETH", …)
      cycle_id      str   — UUID do ciclo atual
      market_data   dict  — OHLCV, volume, regime, indicadores
      signal        dict  — output do Vision: action, confidence, entry, sl, tp
      risk_report   dict  — output do Batman: approved, reasons, adjusted_signal
      execution_result dict — output do IronMan: order_id, fill, pnl
      errors        list  — lista de erros acumulados por nó
      metadata      dict  — timestamp, step_count, source_node
      __current_node str  — nó atual em execução (interno)
      __visited     list  — histórico de nós visitados (interno)
    """

    @classmethod
    def initial(cls, symbol: str, cycle_id: str, market_data: dict | None = None) -> "CycleState":
        """Cria um estado inicial para um ciclo."""
        s = cls()
        s["symbol"] = symbol
        s["cycle_id"] = cycle_id
        s["market_data"] = market_data or {}
        s["signal"] = {}
        s["risk_report"] = {}
        s["execution_result"] = {}
        s["errors"] = []
        s["metadata"] = {
            "created_at": time.monotonic(),
            "step_count": 0,
        }
        s["__current_node"] = ""
        s["__visited"] = []
        return s

    def add_error(self, node: str, error: str) -> None:
        """Registra um erro de nó no estado."""
        self.setdefault("errors", []).append({"node": node, "error": error})

    def mark_visited(self, node: str) -> None:
        self.setdefault("__visited", []).append(node)
        self["__current_node"] = node
        self.setdefault("metadata", {})["step_count"] = (
            self["metadata"].get("step_count", 0) + 1
        )

    @property
    def action(self) -> str:
        """Atalho para signal.action (usado em conditional edges)."""
        return str(self.get("signal", {}).get("action", "HOLD")).upper()

    @property
    def risk_approved(self) -> bool:
        """Atalho para risk_report.approved."""
        return bool(self.get("risk_report", {}).get("approved", False))

    @property
    def has_errors(self) -> bool:
        return len(self.get("errors", [])) > 0


# ---------------------------------------------------------------------------
# CycleGraphNode
# ---------------------------------------------------------------------------

@dataclass
class CycleGraphNode:
    """
    Nó do grafo: nome + função callable.

    A função recebe CycleState e retorna CycleState (pode retornar um dict
    parcial — o resultado é merged no estado existente).
    """
    name: str
    fn: Callable[[CycleState], CycleState | dict]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def execute(self, state: CycleState) -> CycleState:
        """Executa o nó, mergeia o resultado no estado e retorna."""
        state.mark_visited(self.name)
        try:
            result = self.fn(state)
            if isinstance(result, dict):
                state.update(result)
            elif isinstance(result, CycleState):
                state.update(dict(result))
        except Exception as exc:  # noqa: BLE001
            logger.debug("[CycleStateGraph] node %s error: %s", self.name, exc)
            state.add_error(self.name, str(exc))
        return state


# ---------------------------------------------------------------------------
# CycleEdge
# ---------------------------------------------------------------------------

@dataclass
class CycleEdge:
    """Aresta do grafo: src → dst (pode ser END)."""
    src: str
    dst: str  # nome do nó destino, ou "__END__"


# ---------------------------------------------------------------------------
# CycleCompiledGraph
# ---------------------------------------------------------------------------

END = "__END__"
START = "__START__"


class CycleCompiledGraph:
    """
    Grafo compilado — executa o pipeline nó a nó seguindo as arestas.

    Equivalente ao CompiledGraph.invoke() do LangGraph.
    """

    def __init__(
        self,
        nodes: Dict[str, CycleGraphNode],
        edges: List[CycleEdge],
        conditional_edges: List[Tuple[str, Callable, Dict[str, str]]],
        entry_point: str,
        finish_points: List[str],
    ) -> None:
        self._nodes = nodes
        self._edges = edges
        self._conditional_edges = conditional_edges
        self._entry = entry_point
        self._finish = set(finish_points)
        # Build adjacency: src → dst (fixed)
        self._adj: Dict[str, str] = {e.src: e.dst for e in edges}
        # Build conditional adjacency: src → (router_fn, mapping)
        self._cond: Dict[str, Tuple[Callable, Dict[str, str]]] = {
            src: (fn, mapping)
            for src, fn, mapping in conditional_edges
        }

    def _next_node(self, current: str, state: CycleState) -> str:
        """Determina o próximo nó (fixo ou condicional)."""
        # Conditional edge takes priority
        if current in self._cond:
            fn, mapping = self._cond[current]
            try:
                key = fn(state)
            except Exception as exc:  # noqa: BLE001
                logger.debug("[CycleCompiledGraph] router error at %s: %s", current, exc)
                key = "default"
            return mapping.get(key, mapping.get("default", END))
        # Fixed edge
        return self._adj.get(current, END)

    def invoke(self, state: CycleState | dict) -> CycleState:
        """
        Executa o grafo de ponta a ponta e retorna o estado final.

        Equivalente ao CompiledGraph.invoke() do LangGraph.
        """
        if not isinstance(state, CycleState):
            cs = CycleState(state)
        else:
            cs = state

        current = self._entry
        max_steps = 50  # guard contra ciclos infinitos
        steps = 0

        while current not in (END, None) and steps < max_steps:
            node = self._nodes.get(current)
            if node is None:
                logger.debug("[CycleCompiledGraph] unknown node: %s", current)
                break
            cs = node.execute(cs)
            if current in self._finish:
                break
            current = self._next_node(current, cs)
            steps += 1

        cs["metadata"]["total_steps"] = steps
        cs["metadata"]["finished_at"] = time.monotonic()
        return cs

    def stream(self, state: CycleState | dict) -> Iterator[CycleState]:
        """
        Executa o grafo passo a passo, yield do estado após cada nó.

        Equivalente ao CompiledGraph.stream() do LangGraph.
        """
        if not isinstance(state, CycleState):
            cs = CycleState(state)
        else:
            cs = state

        current = self._entry
        max_steps = 50
        steps = 0

        while current not in (END, None) and steps < max_steps:
            node = self._nodes.get(current)
            if node is None:
                break
            cs = node.execute(cs)
            yield CycleState(cs)  # snapshot imutável do estado pós-nó
            if current in self._finish:
                break
            current = self._next_node(current, cs)
            steps += 1


# ---------------------------------------------------------------------------
# CycleStateGraph — builder
# ---------------------------------------------------------------------------

class CycleStateGraph:
    """
    Builder do grafo de estado Mekka Trading.

    Equivalente ao StateGraph do LangGraph:
      graph = CycleStateGraph()
      graph.add_node('vision', vision_fn)
      graph.add_node('batman', batman_fn)
      graph.add_edge('vision', 'batman')
      graph.add_edge('batman', '__END__')
      graph.set_entry_point('vision')
      compiled = graph.compile()
      result = compiled.invoke(CycleState.initial('BTC', cycle_id))
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, CycleGraphNode] = {}
        self._edges: List[CycleEdge] = []
        self._conditional_edges: List[Tuple[str, Callable, Dict[str, str]]] = []
        self._entry: Optional[str] = None
        self._finish: List[str] = []

    def add_node(
        self,
        name: str,
        fn: Callable[[CycleState], CycleState | dict],
        metadata: dict | None = None,
    ) -> "CycleStateGraph":
        """Registra um nó no grafo."""
        self._nodes[name] = CycleGraphNode(name=name, fn=fn, metadata=metadata or {})
        logger.debug("[CycleStateGraph] node added: %s", name)
        return self

    def add_edge(self, src: str, dst: str) -> "CycleStateGraph":
        """Adiciona aresta fixa src → dst."""
        self._edges.append(CycleEdge(src=src, dst=dst))
        return self

    def add_conditional_edges(
        self,
        source: str,
        router_fn: Callable[[CycleState], str],
        path_map: Dict[str, str],
    ) -> "CycleStateGraph":
        """
        Adiciona aresta condicional.

        router_fn(state) → str  (chave no path_map)
        path_map: { "LONG": "batman", "HOLD": "__END__", "default": "batman" }
        """
        self._conditional_edges.append((source, router_fn, path_map))
        return self

    def set_entry_point(self, name: str) -> "CycleStateGraph":
        """Define o nó de entrada do grafo."""
        self._entry = name
        return self

    def set_finish_point(self, name: str) -> "CycleStateGraph":
        """Marca um nó como ponto final (o grafo para após executá-lo)."""
        if name not in self._finish:
            self._finish.append(name)
        return self

    def compile(self) -> CycleCompiledGraph:
        """
        Compila o grafo e retorna um CycleCompiledGraph pronto para invocar.

        Valida que entry_point está definido e que todos os destinos de
        arestas existem como nós ou são __END__.
        """
        if not self._entry:
            raise ValueError("[CycleStateGraph] entry_point não definido — use set_entry_point()")
        if self._entry not in self._nodes:
            raise ValueError(f"[CycleStateGraph] entry_point '{self._entry}' não é um nó registrado")
        # Validate edge destinations
        for edge in self._edges:
            if edge.dst != END and edge.dst not in self._nodes:
                raise ValueError(f"[CycleStateGraph] aresta {edge.src}→{edge.dst}: destino não existe")
        logger.debug(
            "[CycleStateGraph] compiled: %d nodes, %d edges, %d conditional",
            len(self._nodes), len(self._edges), len(self._conditional_edges),
        )
        return CycleCompiledGraph(
            nodes=self._nodes,
            edges=self._edges,
            conditional_edges=self._conditional_edges,
            entry_point=self._entry,
            finish_points=self._finish,
        )

    def summary(self) -> dict:
        return {
            "nodes": list(self._nodes.keys()),
            "edges": [{"src": e.src, "dst": e.dst} for e in self._edges],
            "conditional_edges": [{"src": src} for src, _, _ in self._conditional_edges],
            "entry_point": self._entry,
            "finish_points": self._finish,
        }


# ---------------------------------------------------------------------------
# Factory — grafo padrão Mekka (Vision → Batman → IronMan)
# ---------------------------------------------------------------------------

def build_default_mekka_graph(
    vision_fn: Callable | None = None,
    batman_fn: Callable | None = None,
    ironman_fn: Callable | None = None,
) -> CycleCompiledGraph:
    """
    Constrói o grafo padrão Mekka Trading com 3 nós e edge condicional.

    Vision → [conditional] → Batman → IronMan → END
                         ↘ END  (se action == HOLD)

    Funções de nó padrão são no-ops — substitua pelas implementações reais.
    """
    def _noop(state: CycleState) -> dict:
        return {}

    graph = CycleStateGraph()
    graph.add_node("vision",  vision_fn  or _noop)
    graph.add_node("batman",  batman_fn  or _noop)
    graph.add_node("ironman", ironman_fn or _noop)

    graph.set_entry_point("vision")

    # Vision → conditional: HOLD vai direto para END, LONG/SHORT passa pelo Batman
    graph.add_conditional_edges(
        source="vision",
        router_fn=lambda s: s.action if s.action in ("LONG", "SHORT") else "HOLD",
        path_map={
            "LONG":  "batman",
            "SHORT": "batman",
            "HOLD":  END,
            "default": "batman",
        },
    )

    graph.add_edge("batman",  "ironman")
    graph.add_edge("ironman", END)

    graph.set_finish_point("ironman")

    return graph.compile()
