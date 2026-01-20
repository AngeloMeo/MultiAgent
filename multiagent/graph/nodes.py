# ===========================================================================
#                       NODES - Graph Node Functions
# ===========================================================================
# Funzioni per ogni nodo del grafo LangGraph.
# Ogni funzione riceve lo stato, lo modifica e lo restituisce.
# Per aggiungere nodi: creare funzione e registrarla in graph.py.
# ===========================================================================

import sys
import os
from io import StringIO
from typing import Any

from ..agents.coder import create_coder_agent
from ..agents.tester import create_tester_agent
from ..agents.refiner import create_refiner_agent
from ..models import ErrorReport, TestResult
from ..config import MAX_SYNTAX_RETRIES, MAX_TEST_RETRIES

from .state import AgentState


# ---------------------------------------------------------------------------
#                           CODER NODE
# ---------------------------------------------------------------------------

# Manteniamo un'istanza globale per preservare la history tra chiamate
_coder_agent = None

def get_coder_agent():
    """Singleton per il Coder Agent."""
    global _coder_agent
    if _coder_agent is None:
        _coder_agent = create_coder_agent()
    return _coder_agent


def coder_node(state: AgentState) -> dict:
    """
    Nodo Coder: genera o corregge codice Toy-Agent.
    
    Comportamento:
    - Prima invocazione: genera codice dalla richiesta utente
    - Con syntax_error: corregge l'errore sintattico
    - Con error_report: corregge l'errore logico/runtime
    
    Args:
        state: Stato corrente del grafo
    
    Returns:
        dict: Aggiornamenti allo stato (generated_code, reasoning)
    """
    print("[CODER] Generazione codice...")
    
    coder = get_coder_agent()
    
    # Determina se è prima generazione o correzione
    if state.get("error_report"):
        # Correzione da Refiner (Outer Loop)
        # error_report è già un oggetto ErrorReport (Pydantic)
        code, reasoning = coder.generate_with_error_report(
            state["user_request"], 
            state["error_report"]
        )
    elif state.get("syntax_error"):
        # Correzione sintattica (Inner Loop)
        code, reasoning = coder.generate(
            state["user_request"],
            syntax_error=state["syntax_error"]
        )
    else:
        # Prima generazione
        code, reasoning = coder.generate(state["user_request"])
    
    print(f"[CODER] Codice generato ({len(code)} chars)")
    
    return {
        "generated_code": code,
        "reasoning": reasoning,
        "syntax_error": None,  # Reset errore
        "error_report": None   # Reset errore
    }


# ---------------------------------------------------------------------------
#                           SYNTAX GATE NODE
# ---------------------------------------------------------------------------

def syntax_gate_node(state: AgentState) -> dict:
    """
    Nodo Syntax Gate: valida il codice con ToyParser.
    
    Questo è il filtro deterministico che usa il parser Lark
    per verificare la correttezza sintattica prima di procedere.
    
    Args:
        state: Stato corrente con generated_code
    
    Returns:
        dict: syntax_error (None se OK) e syntax_retry_count aggiornato
    """
    print("[SYNTAX GATE] Validazione sintassi...")
    
    # Import dinamico del ToyParser dalla cartella toy-agent
    current_dir = os.path.dirname(os.path.abspath(__file__))
    toy_agent_path = os.path.join(current_dir, "..", "..", "toy-agent")
    sys.path.insert(0, toy_agent_path)
    
    try:
        from toy_agent import ToyParser
        
        parser = ToyParser()
        ast = parser.parse(state["generated_code"])
        
        print("[SYNTAX GATE] ✓ Sintassi valida!")
        return {
            "syntax_error": None,
            "syntax_retry_count": state["syntax_retry_count"]
        }
        
    except Exception as e:
        error_msg = str(e)
        retry_count = state["syntax_retry_count"] + 1
        
        print(f"[SYNTAX GATE] ✗ Errore: {error_msg}")
        print(f"[SYNTAX GATE] Tentativo {retry_count}/{MAX_SYNTAX_RETRIES}")
        
        return {
            "syntax_error": error_msg,
            "syntax_retry_count": retry_count
        }
    finally:
        # Rimuovi dal path
        if toy_agent_path in sys.path:
            sys.path.remove(toy_agent_path)


# ---------------------------------------------------------------------------
#                           TESTER NODE
# ---------------------------------------------------------------------------

def tester_node(state: AgentState) -> dict:
    """
    Nodo Tester: genera test cases black-box.
    
    Riceve codice sintatticamente valido e produce
    una suite di test con input/output attesi.
    
    Args:
        state: Stato con generated_code valido
    
    Returns:
        dict: test_cases come lista di dict serializzati
    """
    print("[TESTER] Generazione test cases...")
    
    tester = create_tester_agent()
    test_suite = tester.generate_tests(
        state["user_request"],
        state["generated_code"]
    )
    
    # Passa direttamente gli oggetti Pydantic (no serializzazione)
    test_cases = test_suite.test_cases
    
    print(f"[TESTER] Generati {len(test_cases)} test cases")
    
    return {"test_cases": test_cases}


# ---------------------------------------------------------------------------
#                           EXECUTOR NODE
# ---------------------------------------------------------------------------

def executor_node(state: AgentState) -> dict:
    """
    Nodo Executor: esegue i test cases con ToyExecutor.
    
    Per ogni test case:
    1. Configura mock input per "grab"
    2. Esegue il codice
    3. Cattura output da "show"
    4. Confronta con expected_output
    
    Args:
        state: Stato con generated_code e test_cases
    
    Returns:
        dict: test_results con esiti di ogni test
    """
    print("[EXECUTOR] Esecuzione test cases...")
    
    # Import dinamico
    current_dir = os.path.dirname(os.path.abspath(__file__))
    toy_agent_path = os.path.join(current_dir, "..", "..", "toy-agent")
    sys.path.insert(0, toy_agent_path)
    
    results = []
    
    try:
        from toy_agent import ToyExecutor
        import threading
        import queue
        
        EXECUTION_TIMEOUT = 5  # 5 secondi timeout per test
        
        for tc in state["test_cases"]:
            # tc è un oggetto TestCase (Pydantic)
            description = tc.description
            inputs = tc.inputs
            expected = tc.expected_output
            
            print(f"[EXECUTOR] Running: {description}")
            
            try:
                # Mock dell'input
                input_mock = StringIO("\n".join(inputs) + "\n")
                
                # Cattura output
                output_capture = StringIO()
                
                # Salva e sostituisci stdin/stdout
                old_stdin = sys.stdin
                old_stdout = sys.stdout
                sys.stdin = input_mock
                sys.stdout = output_capture
                
                # Esecuzione con timeout usando threading
                result_queue = queue.Queue()
                error_queue = queue.Queue()
                
                def run_executor():
                    try:
                        # Abilita testing_mode per avere output pulito (senza prompt/prefix)
                        executor = ToyExecutor(state["generated_code"], testing_mode=True)
                        result_queue.put(output_capture.getvalue().strip())
                    except Exception as e:
                        error_queue.put(str(e))
                
                thread = threading.Thread(target=run_executor)
                thread.daemon = True
                thread.start()
                thread.join(timeout=EXECUTION_TIMEOUT)
                
                sys.stdin = old_stdin
                sys.stdout = old_stdout
                
                if thread.is_alive():
                    # Timeout - il thread è ancora in esecuzione
                    raise TimeoutError(f"Esecuzione troppo lunga (>{EXECUTION_TIMEOUT}s) - possibile loop infinito")
                
                if not error_queue.empty():
                    raise Exception(error_queue.get())
                
                actual_output = result_queue.get() if not result_queue.empty() else ""
                                
                # Verifica risultato con matching permissivo (sottosequenza)
                # Permette di ignorare righe extra (prompt, log) se il risultato atteso è presente
                expected_lines = [l.strip() for l in expected.strip().splitlines() if l.strip()]
                actual_lines_list = [l.strip() for l in actual_output.splitlines() if l.strip()]
                
                passed = False
                def strict_or_numeric_equal(s1, s2):
                    if s1 == s2: return True
                    try:
                        return abs(float(s1) - float(s2)) < 1e-9
                    except ValueError:
                        return False

                if not expected_lines:
                    passed = not actual_lines_list # Se expected vuoto, actual deve essere vuoto
                else:
                    # Cerca la sequenza expected_lines dentro actual_lines_list
                    # con confronto flessibile (numerico)
                    for i in range(len(actual_lines_list) - len(expected_lines) + 1):
                        match = True
                        for j in range(len(expected_lines)):
                            if not strict_or_numeric_equal(actual_lines_list[i + j], expected_lines[j]):
                                match = False
                                break
                        if match:
                            passed = True
                            break
                
                # Fallback: exact string match (per sicurezza)
                if not passed and actual_output == expected.strip():
                    passed = True
                
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

            except Exception as e:
                # Ripristina stdin/stdout in caso di errore
                sys.stdin = old_stdin if 'old_stdin' in dir() else sys.stdin
                sys.stdout = old_stdout if 'old_stdout' in dir() else sys.stdout
                
                results.append(TestResult(
                    test_description=description,
                    passed=False,
                    actual_output="",
                    expected_output=expected,
                    error_message=str(e)
                ))
                print(f"[EXECUTOR] ✗ ERROR: {str(e)}")
        
    finally:
        if toy_agent_path in sys.path:
            sys.path.remove(toy_agent_path)
    
    return {"test_results": results}


# ---------------------------------------------------------------------------
#                           REFINER NODE
# ---------------------------------------------------------------------------

def refiner_node(state: AgentState) -> dict:
    """
    Nodo Refiner: analizza test falliti e produce error report.
    
    Args:
        state: Stato con test_results (almeno uno fallito)
    
    Returns:
        dict: error_report serializzato e test_retry_count aggiornato
    """
    print("[REFINER] Analisi errori...")
    
    refiner = create_refiner_agent()
    
    # test_results sono già oggetti TestResult (Pydantic)
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
#                           FINAL NODE
# ---------------------------------------------------------------------------

def success_node(state: AgentState) -> dict:
    """
    Nodo Success: tutti i test sono passati.
    
    Returns:
        dict: success=True e messaggio finale
    """
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
    """
    Nodo Failure: superato il limite di tentativi.
    
    Returns:
        dict: success=False e messaggio di errore
    """
    if state["syntax_retry_count"] >= MAX_SYNTAX_RETRIES:
        reason = "Troppi errori di sintassi"
    else:
        reason = "Troppi fallimenti nei test"
    
    print(f"[FAILURE] ✗ {reason}")
    
    # Gestisci None per error_report
    error_report = state.get('error_report')
    if error_report and isinstance(error_report, dict):
        error_details = error_report.get('details', 'N/A')
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
