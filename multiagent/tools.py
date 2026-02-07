# ===========================================================================
#                       TOOLS - LangChain Tool Definitions
# ===========================================================================
# Tools disponibili per il Coder Agent (Knowledge on Demand).
# Permettono accesso mirato alla documentazione senza prompt lunghi.
# ===========================================================================

import os
from langchain_core.tools import tool


# ---------------------------------------------------------------------------
#                           DOCUMENTATION CONTENT
# ---------------------------------------------------------------------------

SYNTAX_DOCS = {
    "general": """
# Toy-Agent: Panoramica Generale

Toy-Agent è un linguaggio imperativo con scope unico (flat).
Struttura base di un programma:

```
memory:
    keep variabile as tipo;
end_memory

task entrypoint [] -> tipo:
    istruzioni;
done
```

REGOLE FONDAMENTALI:
1. Tutti i programmi DEVONO avere un task chiamato "entrypoint"
2. Tutte le variabili DEVONO essere dichiarate nel blocco memory:
3. Ogni statement termina con punto e virgola (;)
4. I blocchi task terminano con "done"
""",

    "types": """
# Tipi di Dato in Toy-Agent

Toy-Agent supporta 4 tipi primitivi:

| Tipo   | Keyword | Esempi          | Default |
|--------|---------|-----------------|---------|
| Intero | whole   | 0, 42, -5       | 0       |
| Float  | fract   | 3.14, 0.5       | 0.0     |
| String | quote   | "hello"         | ""      |
| Bool   | flag    | yes, no         | no      |

DICHIARAZIONE:
```
keep counter as whole;
keep name as quote;
keep active as flag;
```

IMPORTANTE - RESTRIZIONI SUI TIPI:
1. NON esiste type inference
2. NON esiste type casting (es. `x as quote` NON ESISTE)
3. NON puoi convertire whole/fract in quote
4. Gli operatori richiedono tipi omogenei
5. Per mostrare numeri usa `show variabile_numerica;` direttamente

ESEMPIO CORRETTO per mostrare risultati:
```
show result;          % Mostra il valore numerico direttamente
show "Risultato:";    % Messaggio testuale separato
show result;          % Poi il valore
```

ESEMPIO ERRATO (NON FUNZIONA):
```
show "Risultato: " plus result;  % ERRORE: non puoi concatenare quote + whole
show (result as quote);           % ERRORE: casting non esiste
```
""",

    "operators": """
# Operatori in Toy-Agent

ARITMETICI (solo whole/fract omogenei):
- plus   : addizione (a plus b)
- minus  : sottrazione (a minus b)
- times  : moltiplicazione (a times b)
- div    : divisione (a div b)

COMPARAZIONE:
- is     : uguaglianza (a is b)
- is_not : disuguaglianza (a is_not b)
- over   : maggiore (a over b)
- under  : minore (a under b)

LOGICI (solo flag):
- and    : congiunzione (a and b)
- or     : disgiunzione (a or b)
- not    : negazione (not a)

ASSEGNAMENTO:
- <<     : assegna valore (x << 5)

ESEMPIO:
```
result << a plus b times 2;
check result over 10 then ... close;
```
""",

    "control_flow": """
# Controllo di Flusso in Toy-Agent

CONDIZIONALE (check):
```
check condizione then
    istruzioni;
alt_check altra_condizione then
    istruzioni;
alt
    istruzioni_else;
close;
```

ATTENZIONE MASSIMA:
- `alt_check` e `alt` fanno parte dello STESSO blocco `check`.
- NON mettere `close;` prima di `alt_check` o `alt`.
- Un solo `close;` alla fine dell'intera catena.

ESEMPIO CORRETTO (Menu):
```
check choice is 1 then
    show "Uno";
alt_check choice is 2 then
    show "Due";
alt
    show "Altro";
close;  % Unico close finale!
```

ERRORI COMUNI:
```
% ERRATO:
check x is 1 then ... close;
alt_check x is 2 then ... close;  % Sintassi invalida!

% CORRETTO:
check x is 1 then
    ...;
alt_check x is 2 then
    ...;
alt
    ...;
close; % UN SOLO close alla fine della catena!
```

LOOP (loop):
```
loop condizione do
    istruzioni;
close;
```

IMPORTANTE:
- Le condizioni DEVONO essere di tipo flag (yes/no)
- Non sono ammessi interi come booleani
- Ogni blocco termina con "close;"
- NON ESISTE `break`! Per uscire da un loop usa un flag.

ESEMPIO BASE:
```
loop counter under 10 do
    counter << counter plus 1;
    show counter;
close;
```

ESEMPIO USCITA CON FLAG (invece di break):
```
running << yes;
loop running is yes do
    grab choice;
    check choice is 0 then
        running << no;  % Questo fa uscire dal loop!
    close;
close;
```
""",

    "tasks": """
# Task (Funzioni) in Toy-Agent

DEFINIZIONE:
```
task nome_task [param1 as tipo, param2 as tipo] -> tipo_ritorno:
    corpo;
    yield espressione;
done
```

ATTENZIONE - SIGNATURE OBBLIGATORIA:
- OGNI task DEVE avere `-> tipo:` (anche se non ritorna nulla usa `-> whole:`)
- ERRATO: `task entrypoint [] :`
- CORRETTO: `task entrypoint [] -> whole:`

CHIAMATA (come statement):
```
nome_task run [arg1, arg2];
```

CHIAMATA (come espressione):
```
result << nome_task run [arg1, arg2];
```

NOTA: NON usare mai sintassi tipo `call nome_task(arg1, arg2)` - non esiste!

REGOLE:
1. Il task "entrypoint" è obbligatorio e non ha parametri
2. I nomi dei parametri devono essere GLOBALMENTE unici
3. yield restituisce un valore (come return)

ESEMPIO:
```
task sum [a as whole, b as whole] -> whole:
    yield a plus b;
done

task entrypoint [] -> whole:
    result << sum run [5, 3];
    show result;
done
```
""",

    "strings": """
# Stringhe in Toy-Agent

REGOLE STRINGHE:
1. Usare SOLO doppi apici: "testo"
2. NON usare MAI backslash o escape: \\', \\", \\\\
3. NON puoi concatenare quote con altri tipi

CORRETTO:
```
msg << "Hello World";
full << "Hello " plus "World";  % quote + quote OK
```

ERRATO:
```
msg << 'Hello';           % Singoli apici NON supportati
msg << "Hello\\"World";    % Escape NON supportato
msg << "Valore: " plus x; % quote + whole ERRORE
```
""",

    "io": """
# Input/Output in Toy-Agent

OUTPUT (show):
```
show espressione;
```
Stampa il valore dell'espressione.

INPUT (grab):
```
grab variabile;
```
Legge input dall'utente e lo assegna alla variabile.
Il tipo viene convertito automaticamente in base alla dichiarazione.

ESEMPIO:
```
memory:
    keep name as quote;
    keep age as whole;
end_memory

task entrypoint [] -> whole:
    show "Come ti chiami?";
    grab name;
    show "Quanti anni hai?";
    grab age;
    show name;
    show age;
done
```
""",

    "memory": """
# Blocco Memory in Toy-Agent

Il blocco memory dichiara TUTTE le variabili globali del programma.

SINTASSI:
```
memory:
    keep nome1 as tipo1;
    keep nome2 as tipo2;
end_memory
```

REGOLE:
1. Il blocco memory è OBBLIGATORIO (anche se vuoto)
2. Tutte le variabili vanno dichiarate qui
3. Non esistono variabili locali (scope unico)
4. I nomi devono essere univoci in tutto il file

VALORI DEFAULT:
- whole: 0
- fract: 0.0
- quote: ""
- flag: no

ESEMPIO:
```
memory:
    keep counter as whole;
    keep total as fract;
    keep message as quote;
    keep done as flag;
end_memory
```
""",

    "limitations": """
# LIMITAZIONI IMPORTANTI di Toy-Agent

COSE CHE NON ESISTONO IN TOY-AGENT:

1. TYPE CASTING:
   - NON esiste `as quote`, `as whole` etc.
   - NON puoi convertire tra tipi
   - ERRATO: `x as quote`, `(numero as quote)`

2. STRING INTERPOLATION:
   - NON puoi mescolare stringhe e numeri con plus
   - ERRATO: `"Valore: " plus x` dove x è whole
   - CORRETTO: `show "Valore:"; show x;` (due show separati)

3. CONCATENAZIONE TIPI MISTI:
   - `plus` su quote funziona SOLO tra quote
   - ERRATO: `"Hello " plus 5`
   - CORRETTO: `"Hello " plus " World"`

4. VARIABILI:
   - TUTTE le variabili vanno in memory:
   - I parametri task devono avere nomi globalmente unici

5. OPERATORI ALTERNATIVI:
   - NON esistono: +, -, *, /, ==, !=, <, >, &&, ||, !
   - USA: plus, minus, times, div, is, is_not, under, over, and, or, not

6. RETURN STATEMENT:
   - NON esiste `return`
   - USA: `yield espressione;`

7. RICORSIONE:
   - LA RICORSIONE NON FUNZIONA per via dello scope unico
   - I parametri dei task sono GLOBALI, quindi vengono sovrascritti nelle chiamate ricorsive
   - ERRATO: `factorial run [n minus 1]` (il parametro n viene sovrascritto)
   - USA SEMPRE loop (while) invece della ricorsione

8. COMMENTI:
   - I commenti usano `%` NON `#`
   - ERRATO: `# questo è un commento`
   - CORRETTO: `% questo è un commento`

9. SINTASSI MEMORY BLOCK:
   - OGNI variabile DEVE iniziare con `keep`
   - ERRATO: `variabile as whole;`
   - CORRETTO: `keep variabile as whole;`

ESEMPIO CORRETTO - Fattoriale:
```
memory:
    keep n as whole;
    keep result as whole;
    keep i as whole;
end_memory

task entrypoint [] -> whole:
    grab n;  % NO prompt! Solo grab diretto
    
    result << 1;
    i << 1;
    
    loop i under n plus 1 do
        result << result times i;
        i << i plus 1;
    close;
    
    % OUTPUT: solo valori grezzi, MAI frasi descrittive
    show result;
done
```

ERRORI COMUNI DA EVITARE:
```
% TUTTO QUESTO È ERRATO:
x_str << x;                     % ERRATO: non puoi assegnare whole a quote
show "Valore: " plus x;         % ERRATO: non puoi concatenare quote + whole
show x plus " unità";           % ERRATO: non puoi concatenare whole + quote
x_as_quote << x;                % ERRATO: non esiste conversione di tipi
```
"""
}


# ---------------------------------------------------------------------------
#                           TOOL DEFINITIONS
# ---------------------------------------------------------------------------

@tool
def get_syntax_help(topic: str) -> str:
    """
    Ottieni documentazione sulla sintassi del linguaggio Toy-Agent.
    
    Usa questo tool PRIMA di scrivere codice per consultare la sintassi corretta.
    
    Args:
        topic: Argomento da consultare. Valori possibili:
               - "limitations": IMPORTANTE! Cosa NON esiste nel linguaggio
               - "general": panoramica del linguaggio
               - "types": tipi di dato (whole, fract, quote, flag)
               - "operators": operatori aritmetici, logici, comparazione
               - "control_flow": check/alt, loop (include pattern uscita con flag)
               - "tasks": definizione e chiamata di task (signature obbligatoria)
               - "strings": regole stringhe e escape (VIETATI)
               - "io": show e grab
               - "memory": blocco dichiarazioni variabili
    
    Returns:
        Documentazione formattata per l'argomento richiesto.
    """
    topic_clean = topic.strip()
    
    if topic_clean in SYNTAX_DOCS:
        return SYNTAX_DOCS[topic_clean]
    
    # Se topic non riconosciuto, restituisce lista argomenti disponibili
    available = ", ".join(SYNTAX_DOCS.keys())
    return f"Topic '{topic}' non trovato. Argomenti disponibili: {available}"


@tool
def get_full_grammar() -> str:
    """
    Ottieni la grammatica EBNF completa del linguaggio Toy-Agent.
    
    Usa questo tool solo se hai bisogno di dettagli precisi sulla grammatica formale.
    Per uso normale, preferisci get_syntax_help con topic specifici.
    
    Returns:
        Grammatica Lark/EBNF del linguaggio.
    """
    import os
    import requests
    
    api_url = os.environ.get("TOY_AGENT_API_URL")
    
    if not api_url:
        return "Errore: API URL non configurato (TOY_AGENT_API_URL mancante)"
    
    try:
        response = requests.get(f"{api_url}/grammar", timeout=10)
        if response.status_code == 200:
            return response.text
        else:
            return f"Errore: API ha restituito status {response.status_code}"
    except requests.exceptions.RequestException as e:
        return f"Errore di connessione: {e}"


# ---------------------------------------------------------------------------
#                           TOOLS LIST FOR BINDING
# ---------------------------------------------------------------------------
# Lista di tutti i tools da bindare al Coder Agent.

CODER_TOOLS = [get_syntax_help, get_full_grammar]
