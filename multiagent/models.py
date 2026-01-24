# ===========================================================================
#                       MODELS - Pydantic Schemas
# ===========================================================================
# Schema dati strutturati per comunicazione tra agenti.
# Pydantic garantisce validazione e serializzazione automatica.
# Per aggiungere campi: modifica le classi BaseModel qui sotto.
# ===========================================================================

from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
#                           ERROR TYPE ENUM
# ---------------------------------------------------------------------------

class ErrorType(str, Enum):
    """Enum per i tipi di errore supportati dal sistema."""
    SYNTAX = "Syntax"
    RUNTIME = "Runtime"
    LOGICAL = "Logical"


# ---------------------------------------------------------------------------
#                           ERROR REPORTING
# ---------------------------------------------------------------------------
# Usato dal Refiner Agent per comunicare errori in modo strutturato.

class ErrorReport(BaseModel):
    """
    Report strutturato degli errori rilevati durante parsing o esecuzione.
    
    Attributes:
        error_type: Tipo di errore (Syntax/Runtime/Logical)
        details: Descrizione dettagliata dell'errore
        location: Posizione opzionale nel codice (es. "line 5")
        suggestion: Suggerimento per la correzione
    """
    error_type: ErrorType = Field(
        description="Categoria dell'errore: Syntax (parsing), Runtime (esecuzione), Logical (output errato)"
    )
    details: str = Field(
        description="Descrizione dettagliata dell'errore riscontrato"
    )
    location: Optional[str] = Field(
        default=None,
        description="Posizione nel codice dove si è verificato l'errore"
    )
    suggestion: str = Field(
        description="Suggerimento specifico per correggere l'errore"
    )


# ---------------------------------------------------------------------------
#                           TEST CASE SPECIFICATION
# ---------------------------------------------------------------------------
# Usato dal Tester Agent per definire casi di test in formato JSON.

class TestCase(BaseModel):
    """
    Specifica di un singolo caso di test (Black Box).
    
    Attributes:
        description: Breve descrizione del test
        inputs: Valori da fornire al programma (simulati via mock di grab)
        expected_output: Output atteso dal programma (da show)
    """
    description: str = Field(
        description="Descrizione breve del caso di test"
    )
    inputs: list[str] = Field(
        default_factory=list,
        description="Lista di input da fornire in ordine (per grab)"
    )
    expected_output: str = Field(
        description="Output atteso dalla esecuzione (stringa di show)"
    )


class TestSuite(BaseModel):
    """
    Suite completa di test cases generata dal Tester Agent.
    """
    test_cases: list[TestCase] = Field(
        description="Lista di casi di test da eseguire"
    )


# ---------------------------------------------------------------------------
#                           CODER OUTPUT
# ---------------------------------------------------------------------------
# Output strutturato del Coder Agent.

class CoderOutput(BaseModel):
    """
    Output del Coder Agent contenente codice e ragionamento.
    
    Attributes:
        toy_code: Codice Toy-Agent generato
        reasoning: Spiegazione del ragionamento seguito
    """
    toy_code: str = Field(
        description="Codice Toy-Agent completo e sintatticamente valido"
    )
    reasoning: str = Field(
        description="Spiegazione del ragionamento e delle scelte implementative"
    )


# ---------------------------------------------------------------------------
#                           TEST EXECUTION RESULT
# ---------------------------------------------------------------------------
# Risultato dell'esecuzione di un singolo test.

class TestResult(BaseModel):
    """
    Risultato dell'esecuzione di un singolo test case.
    
    Attributes:
        test_description: Descrizione del test eseguito
        passed: True se il test è passato
        actual_output: Output effettivo del programma
        expected_output: Output atteso
        error_message: Messaggio di errore se fallito
    """
    test_description: str
    passed: bool
    actual_output: str
    expected_output: str
    error_message: Optional[str] = None
