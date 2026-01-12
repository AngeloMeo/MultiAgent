# Definizione Nodi AST: Toy-Agent

Data la natura "flat" del linguaggio, l'AST è molto più semplice rispetto a linguaggi standard.

## Nodi Principali

**ProgramNode**
* `memoryBlock`: List<VarDeclNode>
* `taskList`: List<TaskNode>

**VarDeclNode** (Usato solo nella sezione Memory)
* `identifier`: String
* `type`: Enum (WHOLE, FRACT, QUOTE, FLAG)

**TaskNode**
* `name`: String
* `params`: List<VarDeclNode> (Nota: questi vanno controllati per collisioni globali)
* `returnType`: Enum
* `body`: BodyNode

## Nodi Istruzioni (Statements)

**BodyNode**
* `statements`: List<StatNode>

**AssignNode**
* `target`: IdentifierNode
* `value`: ExprNode

**YieldNode**
* `expression`: ExprNode

**CheckNode** (If-Else)
* `condition`: ExprNode (Must be FLAG)
* `thenBody`: BodyNode
* `elifList`: List<ElifNode>
* `elseBody`: BodyNode (Optional)

**LoopNode** (While)
* `condition`: ExprNode (Must be FLAG)
* `body`: BodyNode

## Nodi Espressioni

**BinaryOpNode**
* `left`: ExprNode
* `operator`: Enum (PLUS, MINUS, IS, OVER, AND...)
* `right`: ExprNode

**TaskCallNode**
* `taskName`: String
* `args`: List<ExprNode>