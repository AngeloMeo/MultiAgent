# ===========================================================================
#                       NODES - Graph Node Functions
# ===========================================================================
# Funzioni nodo per il grafo LangGraph.
# Ogni funzione riceve lo stato, lo modifica e lo restituisce.
# Include nodi per: Coder (subgraph), Syntax Gate, Tester, Executor, 
# Refiner, Success, Failure.
# ===========================================================================

from typing import Literal

import requests
from langchain_core.messages import SystemMessage

from ..agents.coder import create_coder_agent, CODER_SYSTEM_PROMPT
from ..agents.tester import create_tester_agent
from ..agents.refiner import create_refiner_agent
from ..models import TestResult, ErrorReport, ErrorType
from ..config import (
    MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES, 
    TOY_AGENT_API_URL, EXECUTION_TIMEOUT
)

from .state import AgentState

# Import opzionale del modulo di esecuzione locale
try:
    from .local_executor import local_parse, local_execute
    LOCAL_EXECUTOR_AVAILABLE = True
except ImportError:
    LOCAL_EXECUTOR_AVAILABLE = False
    local_parse = None
    local_execute = None


# ---------------------------------------------------------------------------
#                           HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def _strict_or_numeric_equal(s1: str, s2: str) -> bool:
    """Confronta due stringhe, con tolleranza numerica."""
    if s1 == s2:
        return True
    try:
        return abs(float(s1) - float(s2)) < 1e-9
    except ValueError:
        return False


def _verify_output(actual: str, expected: str) -> bool:
    """
    Verifica se l'output atteso è contenuto nell'output effettivo.
    
    Supporta "Newline Magic String" Strategy:
    Poiché Toy-Agent non può concatenare stringhe e numeri facilmente e aggiunge
    sempre newline, la strategia è:
    1. Stampare il token ">>>" su una riga
    2. Stampare il risultato sulla riga successiva
    
    Il verificatore cerca ">>>" e prende la riga DOPO come valore da testare.
    
    Esempio:
        actual: "Menu...\n>>>\n15\nMenu..."
        expected: "15"
        -> True
    """
    raw_lines = [l.strip() for l in actual.splitlines() if l.strip()]
    magic_values = []
    
    i = 0
    while i < len(raw_lines):
        line = raw_lines[i]
        # Se la riga è il magic token (o inizia con esso)
        if line.startswith(">>>"):
            # ">>>" e valore alla riga dopo (Newline Strategy)
            if i + 1 < len(raw_lines):
                magic_values.append(raw_lines[i+1])
                i += 1 # Salta la riga del valore
        i += 1
            
    if magic_values:
        actual_lines = magic_values
    else:
        # Fallback: usa tutto l'output
        actual_lines = raw_lines
        
    expected_lines = [l.strip() for l in expected.strip().splitlines() if l.strip()]
    
    if not expected_lines:
        return not actual_lines
    
    # Cerca ogni expected line come sottosequenza (non contigua) nell'actual
    actual_idx = 0
    for expected_line in expected_lines:
        found = False
        while actual_idx < len(actual_lines):
            if _strict_or_numeric_equal(actual_lines[actual_idx], expected_line):
                found = True
                actual_idx += 1
                break
            actual_idx += 1
        
        if not found:
            # Fallback: cerca ovunque (non in ordine) per valori critici
            if not any(_strict_or_numeric_equal(al, expected_line) for al in actual_lines):
                return False
    
    return True


def _parse_code(script: str) -> tuple[bool, str | None]:
    """
    Valida il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (success, error_msg): success=True se sintassi valida, 
        altrimenti error_msg contiene l'errore.
    """
    # Prova remoto
    if TOY_AGENT_API_URL:
        try:
            print(f"[PARSE] 🚀 Parsing remoto")
            response = requests.post(
                f"{TOY_AGENT_API_URL}/parse",
                json={"script": script},
                timeout=EXECUTION_TIMEOUT
            )
            
            # Server error (5xx) -> fallback
            if response.status_code >= 500:
                print(f"[PARSE] ⚠ Server error ({response.status_code}), fallback a locale...")
            # HTML response (Azure sleeping) -> fallback
            elif "<html" in response.text.lower():
                print("[PARSE] ⚠ API risponde con HTML, fallback a locale...")
            elif response.status_code == 200:
                return True, None
            else:
                # Errore di sintassi (4xx)
                try:
                    error_msg = response.json().get("error", "Unknown syntax error")
                except ValueError:
                    error_msg = response.text[:200]
                return False, error_msg
                
        except requests.exceptions.RequestException as e:
            print(f"[PARSE] ⚠ Connessione fallita ({e}), fallback a locale...")
    
    # Fallback locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        return False, "API non disponibile e modulo locale non presente"
    
    return local_parse(script)


def _execute_code(script: str, inputs: list) -> tuple[str, str | None]:
    """
    Esegue il codice: prova remoto, fallback a locale se necessario.
    
    Returns:
        Tuple (output, error): output è l'output del programma,
        error è None se esecuzione OK, altrimenti contiene l'errore.
    """
    # Prova remoto
    if TOY_AGENT_API_URL:
        try:
            print(f"[EXECUTE] 🚀 Esecuzione remota")
            response = requests.post(
                f"{TOY_AGENT_API_URL}/run",
                json={"script": script, "inputs": inputs},
                timeout=EXECUTION_TIMEOUT
            )
            
            if response.status_code >= 500:
                print(f"[EXECUTE] ⚠ Server error ({response.status_code}), fallback a locale...")
            else:
                try:
                    resp_data = response.json()
                except ValueError:
                    if "<html" in response.text.lower():
                        print("[EXECUTE] ⚠ API risponde con HTML, fallback a locale...")
                    else:
                        return "", f"Invalid response: {response.text[:200]}"
                else:
                    output_list = resp_data.get("output", [])
                    output = "\n".join(output_list) if isinstance(output_list, list) else str(output_list)
                    
                    if response.status_code == 200:
                        return output, None
                    else:
                        return output, resp_data.get("error", "Unknown execution error")
                        
        except requests.exceptions.RequestException as e:
            print(f"[EXECUTE] ⚠ Connessione fallita ({e}), fallback a locale...")
    
    # Fallback locale
    if not LOCAL_EXECUTOR_AVAILABLE:
        return "", "API non disponibile e modulo locale non presente"
    
    return local_execute(script, inputs)


# ---------------------------------------------------------------------------
#                           CODER SUBGRAPH NODES
# ---------------------------------------------------------------------------

def coder_reasoning_node(state: AgentState) -> dict:
    """
    Nodo di ragionamento del Coder: chiama coder.reason() per tool exploration.
    
    Adapter tra AgentState e CoderAgent.
    """
    coder = create_coder_agent()
    messages = list(state.get("messages", []))
    
    # Inizializza con SystemMessage se vuoto
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=CODER_SYSTEM_PROMPT)] + messages
    
    response = coder.reason(messages, state)
    messages.append(response)
    
    return {"messages": messages}


def coder_structuring_node(state: AgentState) -> dict:
    """
    Nodo di strutturazione del Coder: chiama coder.structure() per output JSON.
    
    Adapter tra AgentState e CoderAgent.
    """
    coder = create_coder_agent()
    messages = list(state.get("messages", []))
    
    result = coder.structure(messages)
    
    return {
        "generated_code": result.toy_code,
        "reasoning": result.reasoning,
        "error_report": None,
    }


def after_reasoning(state: AgentState) -> Literal["tools", "structure"]:
    """
    Routing dopo reasoning: se ci sono tool calls -> tools, altrimenti -> structure.
    """
    messages = state.get("messages", [])
    if not messages:
        return "structure"
    
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    
    return "structure"


# ---------------------------------------------------------------------------
#                           SYNTAX GATE NODE
# ---------------------------------------------------------------------------


def syntax_gate_node(state: AgentState) -> dict:
    """Nodo Syntax Gate: valida il codice con ToyParser."""
    print("[SYNTAX GATE] Validazione sintassi...")
    
    success, error_msg = _parse_code(state["generated_code"])
    
    if success:
        print("[SYNTAX GATE] ✓ Sintassi valida!")
        return {
            "error_report": None,
            "syntax_retry_count": 0
        }
    else:
        retry_count = state["syntax_retry_count"] + 1
        print(f"[SYNTAX GATE] ✗ Errore: {error_msg}")
        print(f"[SYNTAX GATE] Tentativo {retry_count}/{MAX_SYNTAX_RETRIES}")
        return {
            "error_report": ErrorReport(
                error_type=ErrorType.SYNTAX,
                details=error_msg,
                location=None,
                suggestion="Correggi la sintassi del codice."
            ),
            "syntax_retry_count": retry_count
        }


# ---------------------------------------------------------------------------
#                           TESTER NODE
# ---------------------------------------------------------------------------

def tester_node(state: AgentState) -> dict:
    """Nodo Tester: genera test cases black-box."""
    print("[TESTER] Generazione test cases...")
    
    tester = create_tester_agent()
    test_suite = tester.generate_tests(
        state["user_request"],
        state["generated_code"]
    )
    
    test_cases = test_suite.test_cases
    print(f"[TESTER] Generati {len(test_cases)} test cases")
    
    return {"test_cases": test_cases}


# ---------------------------------------------------------------------------
#                           EXECUTOR NODE
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> dict:
    """Nodo Executor: esegue i test cases con ToyExecutor."""
    print("[EXECUTOR] Esecuzione test cases...")
    
    results = []
    
    for tc in state["test_cases"]:
        description = tc.description
        inputs = tc.inputs
        expected = tc.expected_output
        
        print(f"[EXECUTOR] Running: {description}")
        
        actual_output, error = _execute_code(state["generated_code"], inputs)
        
        if error:
            results.append(TestResult(
                test_description=description,
                passed=False,
                actual_output=actual_output,
                expected_output=expected,
                error_message=error
            ))
            print(f"[EXECUTOR] ✗ ERROR: {error}")
        else:
            passed = _verify_output(actual_output, expected)
            
            results.append(TestResult(
                test_description=description,
                passed=passed,
                actual_output=actual_output,
                expected_output=expected,
                error_message=None if passed else "Output mismatch"
            ))
            
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"[EXECUTOR] {status}")
            
            if not passed:
                print(f"  [EXPECTED]: {repr(expected)}")
                print(f"  [ACTUAL]  : {repr(actual_output)}")
    
    return {"test_results": results}


# ---------------------------------------------------------------------------
#                           REFINER NODE
# ---------------------------------------------------------------------------

def refiner_node(state: AgentState) -> dict:
    """Nodo Refiner: analizza test falliti e produce error report."""
    print("[REFINER] Analisi errori...")
    
    refiner = create_refiner_agent()
    test_results = state["test_results"]
    
    error_report = refiner.analyze_failure(
        state["user_request"],
        state["generated_code"],
        test_results
    )
    
    retry_count = state["test_retry_count"] + 1
    print(f"[REFINER] Errore: {error_report.error_type}")
    print(f"[REFINER] Suggerimento: {error_report.suggestion}")
    print(f"[REFINER] Tentativo {retry_count}/{MAX_TEST_RETRIES}")
    
    return {
        "error_report": error_report,
        "test_retry_count": retry_count
    }


# ---------------------------------------------------------------------------
#                           FINAL NODES
# ---------------------------------------------------------------------------

def success_node(state: AgentState) -> dict:
    """Nodo Success: tutti i test sono passati."""
    print("[SUCCESS] ✓ Tutti i test passati!")
    
    return {
        "success": True,
        "final_output": f"""✓ Codice generato con successo!

CODICE TOY-AGENT:
{state['generated_code']}

REASONING:
{state['reasoning']}
"""
    }


def failure_node(state: AgentState) -> dict:
    """Nodo Failure: superato il limite di tentativi."""
    if state["syntax_retry_count"] >= MAX_SYNTAX_RETRIES:
        reason = "Troppi errori di sintassi"
    else:
        reason = "Troppi fallimenti nei test"
    
    print(f"[FAILURE] ✗ {reason}")
    
    # Estrai dettagli errore (priorità: error_report > test_results > syntax_error)
    error_report = state.get('error_report')
    failed_tests = [r for r in state.get("test_results", []) if not r.passed]
    
    if error_report:
        error_details = getattr(error_report, 'details', None) or error_report.get('details', 'N/A')
    elif failed_tests:
        ft = failed_tests[0]
        error_details = f"Test Failed: {ft.test_description}\nExpected: {ft.expected_output}\nActual: {ft.actual_output or 'N/A'}"
    else:
        error_details = state.get('syntax_error') or 'N/A'
    
    return {
        "success": False,
        "final_output": f"""✗ Generazione fallita: {reason}

Ultimo codice tentato:
{state['generated_code']}

Ultimo errore:
{error_details}
"""
    }
