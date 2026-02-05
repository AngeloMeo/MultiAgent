# 🤖 Multi-Agent Toy-Language Generator
**Progetto per il corso di Ingegneria dei Linguaggi di Programmazione**  
*Prof. G. Costagliola*

Un sistema multi-agente autonomo in grado di generare, validare, testare e correggere codice scritto nel linguaggio proprietario **Toy-Agent**.

![Architecture Logic](https://placehold.co/800x200?text=Coder+%E2%86%92+Syntax+Gate+%E2%86%92+Executor+%E2%86%92+Refiner)

## 🚀 Tecnologie Utilizzate

Il progetto integra tecniche avanzate di **Agentic AI** e **Language Engineering**:

*   **LangGraph**: Orchestrazione del flusso di controllo ciclico degli agenti (State Machine).
*   **Lark**: Parsing e validazione sintattica del linguaggio Toy-Agent (CFG Grammar).
*   **LLM (Gemini 2.5 Flash Lite)**: Motore di ragionamento per generazione codice (Coder), testing (Tester) e debugging (Refiner).
*   **Pydantic**: Validazione strutturata dei dati scambiati tra gli agenti (Output Parsing).
*   **Python 3.14**: Runtime environment.

## 🛠️ Quickstart

### 1. Prerequisiti
*   Python 3.14 installato.
*   Una API Key di Google Generative AI (Gemini).

### 2. Installazione
```bash
# Clona il repository
git clone <url-repo>
cd <repo-folder>

# Crea environment virtuale
python -m venv .venv
# Windows
.venv\Scripts\activate
# Mac/Linux
source .venv/bin/activate

# Installa dipendenze
pip install -r requirements.txt
```

### 3. Configurazione
Creare un file `.env` nella root del progetto:
```ini
GOOGLE_API_KEY=tua_chiave_api_qui
TOY_AGENT_API_URL=api_link_qui
```

### 4. Esecuzione
Lancia il sistema chiedendo di generare un programma. Esempio:

```bash
python main.py "Scrivi un programma che calcola il fattoriale di 5"
```

Per eseguire una Suite di Test Predefiniti:
```bash
python main.py
```

## 🧠 Architettura Multi-Agente

Il sistema implementa un ciclo **ReAct** ibrido con correzione automatica:

1.  **Coder Agent**: Scrive il codice consultando la documentazione tramite Tools.
2.  **Syntax Gate**: Il parser Lark valida la sintassi. Se fallisce, il Coder corregge subito (Inner Loop).
3.  **Tester Agent**: Genera casi di test black-box (Input/Output atteso).
4.  **Toy Executor**: Esegue il codice in un ambiente sandbox sicuro.
5.  **Refiner Agent**: Se i test falliscono, analizza l'errore runtime/logico e guida il Coder nella correzione (Outer Loop).

---
*Progetto sviluppato da Angelo Meo*
