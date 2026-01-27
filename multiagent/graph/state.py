# ===========================================================================
#                       STATE - Graph State Schema
# ===========================================================================
# Definizione dello stato condiviso tra tutti i nodi del grafo.
# TypedDict garantisce type safety e documentazione del flusso dati.
# Per aggiungere campi: modificare AgentState e aggiornare i nodi.
# ===========================================================================

from typing import TypedDict, Optional

from ..models import ErrorReport, TestCase, TestResult


# ---------------------------------------------------------------------------
#                           AGENT STATE
# ---------------------------------------------------------------------------

class AgentState(TypedDict):
    """
    Stato condiviso tra tutti i nodi del grafo LangGraph.
    
    Questo TypedDict rappresenta la memoria persistente che fluisce
    attraverso i nodi del grafo, accumulando informazioni ad ogni step.
    
    Attributes:
        user_request: Richiesta originale dell'utente
        generated_code: Codice Toy-Agent generato dal Coder
        reasoning: Spiegazione del Coder sulle scelte implementative
        syntax_error: Ultimo errore di sintassi (se presente)
        test_cases: Lista di test cases generati dal Tester
        test_results: Risultati dell'esecuzione dei test
        error_report: Report di errore dal Refiner (se presente)
        syntax_retry_count: Contatore tentativi Inner Loop
        test_retry_count: Contatore tentativi Outer Loop
        success: Flag di completamento con successo
        final_output: Messaggio finale per l'utente
    """
    
    # Input iniziale
    user_request: str
    
    # Output del Coder
    generated_code: str
    reasoning: str
    
    # Syntax Gate (Inner Loop)
    syntax_error: Optional[str]
    syntax_retry_count: int
    
    # Test Generation
    test_cases: list[TestCase]
    
    # Test Execution
    test_results: list[TestResult]
    
    # Refiner Output
    error_report: Optional[ErrorReport]
    test_retry_count: int
    
    # Final State
    success: bool
    final_output: str


# ---------------------------------------------------------------------------
#                           INITIAL STATE
# ---------------------------------------------------------------------------

def create_initial_state(user_request: str) -> AgentState:
    """
    Crea lo stato iniziale del grafo per una nuova richiesta.
    
    Args:
        user_request: La richiesta dell'utente da elaborare.
    
    Returns:
        AgentState: Stato iniziale con tutti i campi inizializzati.
    """
    return AgentState(
        #Input iniziale
        user_request=user_request,
        # Output del Coder
        generated_code="",
        reasoning="",
        # Syntax Gate (Inner Loop)
        syntax_error=None,
        syntax_retry_count=0,
        # Test Generation
        test_cases=[],
        # Test Execution
        test_results=[],
        # Refiner Output
        error_report=None,
        test_retry_count=0,
        # Final State
        success=False,
        final_output=""
    )
