# ===========================================================================
#                       GRAPH - LangGraph Composition
# ===========================================================================
# Composizione del grafo con nodi e edges condizionali.
# Definisce Inner Loop (syntax) e Outer Loop (test execution).
# ===========================================================================

from langgraph.graph import StateGraph, END

from ..config import MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES
from .state import AgentState, create_initial_state
from .nodes import (
    coder_node,
    syntax_gate_node,
    tester_node,
    executor_node,
    refiner_node,
    success_node,
    failure_node
)


# ---------------------------------------------------------------------------
#                           CONDITIONAL EDGES
# ---------------------------------------------------------------------------

def after_syntax_gate(state: AgentState) -> str:
    """
    Decisione dopo il Syntax Gate.
    
    Returns:
        "tester" se sintassi OK
        "coder" se errore e tentativi disponibili
        "failure" se superato limite tentativi
    """
    if state["syntax_error"] is None:
        # Sintassi OK -> vai al Tester
        return "tester"
    elif state["syntax_retry_count"] >= MAX_SYNTAX_RETRIES:
        # Troppi errori -> fallimento
        return "failure"
    else:
        # Errore recuperabile -> riprova
        return "coder"


def after_executor(state: AgentState) -> str:
    """
    Decisione dopo l'Executor.
    
    Returns:
        "success" se tutti i test passati
        "refiner" se ci sono fallimenti e tentativi disponibili
        "failure" se superato limite tentativi
    """
    # Guard: se non ci sono test, considera come fallimento
    if not state["test_results"]:
        print("[EXECUTOR] WARNING: Nessun test case eseguito!")
        if state["test_retry_count"] >= MAX_TEST_RETRIES:
            return "failure"
        return "refiner"
    
    # Controlla se tutti i test sono passati (tr è un oggetto TestResult Pydantic)
    all_passed = all(tr.passed for tr in state["test_results"])
    
    if all_passed:
        return "success"
    elif state["test_retry_count"] >= MAX_TEST_RETRIES:
        return "failure"
    else:
        return "refiner"


# ---------------------------------------------------------------------------
#                           GRAPH BUILDER
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Costruisce il grafo LangGraph completo.
    
    Struttura:
    
    INNER LOOP (Syntax Correction):
        coder -> syntax_gate -> [OK] -> tester
                             -> [ERROR] -> coder (loop)
    
    OUTER LOOP (Test Correction):
        tester -> executor -> [PASS] -> success
                           -> [FAIL] -> refiner -> coder (loop)
    
    Returns:
        StateGraph: Grafo compilato pronto per l'esecuzione.
    """
    # Crea il builder
    graph_builder = StateGraph(AgentState)
    
    # --- REGISTRAZIONE NODI ---
    graph_builder.add_node("coder", coder_node)
    graph_builder.add_node("syntax_gate", syntax_gate_node)
    graph_builder.add_node("tester", tester_node)
    graph_builder.add_node("executor", executor_node)
    graph_builder.add_node("refiner", refiner_node)
    graph_builder.add_node("success", success_node)
    graph_builder.add_node("failure", failure_node)
    
    # --- EDGE DIRETTI ---
    # Start -> Coder
    graph_builder.set_entry_point("coder")
    
    # Coder -> Syntax Gate (sempre)
    graph_builder.add_edge("coder", "syntax_gate")
    
    # Tester -> Executor (sempre)
    graph_builder.add_edge("tester", "executor")
    
    # Refiner -> Coder (sempre - loop esterno)
    graph_builder.add_edge("refiner", "coder")
    
    # Success/Failure -> END
    graph_builder.add_edge("success", END)
    graph_builder.add_edge("failure", END)
    
    # --- EDGE CONDIZIONALI ---
    # Dopo Syntax Gate: OK -> Tester, Error -> Coder o Failure
    graph_builder.add_conditional_edges(
        "syntax_gate",
        after_syntax_gate,
        {
            "tester": "tester",
            "coder": "coder",
            "failure": "failure"
        }
    )
    
    # Dopo Executor: Pass -> Success, Fail -> Refiner o Failure
    graph_builder.add_conditional_edges(
        "executor",
        after_executor,
        {
            "success": "success",
            "refiner": "refiner",
            "failure": "failure"
        }
    )
    
    # Compila il grafo
    return graph_builder.compile()


# ---------------------------------------------------------------------------
#                           GRAPH RUNNER
# ---------------------------------------------------------------------------

def run_graph(user_request: str) -> dict:
    """
    Esegue il grafo completo per una richiesta utente.
    
    Args:
        user_request: Descrizione del programma da generare
    
    Returns:
        dict: Stato finale con success, generated_code, final_output
    """
    print("=" * 60)
    print("MULTI-AGENT TOY-AGENT CODE GENERATOR")
    print("=" * 60)
    print(f"Richiesta: {user_request}")
    print("=" * 60)
    
    # Crea stato iniziale
    initial_state = create_initial_state(user_request)
    
    # Costruisci ed esegui il grafo
    graph = build_graph()
    final_state = graph.invoke(initial_state)
    
    print("=" * 60)
    print("RISULTATO FINALE")
    print("=" * 60)
    print(final_state["final_output"])
    
    return final_state


# ---------------------------------------------------------------------------
#                           EXPORT
# ---------------------------------------------------------------------------

__all__ = ["build_graph", "run_graph"]
