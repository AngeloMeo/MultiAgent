import sys
import os
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Dict, Any, Optional

from lark import Lark
from lark.visitors import Interpreter

# ==========================================
#              AST DEFINITIONS
# ==========================================

class TypeName(Enum):
    WHOLE = auto()
    FRACT = auto()
    QUOTE = auto()
    FLAG = auto()

@dataclass
class ASTNode:
    pass

@dataclass
class ProgramNode(ASTNode):
    memory_block: List['VarDeclNode']
    task_list: List['TaskNode']

@dataclass
class VarDeclNode(ASTNode):
    name: str
    type_name: TypeName

@dataclass
class TaskNode(ASTNode):
    name: str
    params: List[VarDeclNode]
    return_type: TypeName
    body: 'BodyNode'

@dataclass
class BodyNode(ASTNode):
    statements: List['StatNode']

class StatNode(ASTNode): pass

@dataclass
class AssignmentNode(StatNode):
    target: str
    expr: 'ExprNode'

@dataclass
class TaskCallStatNode(StatNode):
    task_name: str
    args: List['ExprNode']

@dataclass
class YieldNode(StatNode):
    expr: 'ExprNode'

@dataclass
class ShowNode(StatNode):
    expr: 'ExprNode'

@dataclass
class GrabNode(StatNode):
    target: str

@dataclass
class CheckNode(StatNode):
    condition: 'ExprNode'
    then_body: BodyNode
    elif_blocks: List['ElifNode']
    else_body: Optional[BodyNode]

@dataclass
class ElifNode(ASTNode):
    condition: 'ExprNode'
    body: BodyNode

@dataclass
class LoopNode(StatNode):
    condition: 'ExprNode'
    body: BodyNode

class ExprNode(ASTNode): pass

@dataclass
class BinaryOpNode(ExprNode):
    left: ExprNode
    op: str
    right: ExprNode

@dataclass
class UnaryOpNode(ExprNode):
    op: str
    expr: ExprNode

@dataclass
class TaskCallExprNode(ExprNode):
    task_name: str
    args: List[ExprNode]

@dataclass
class AtomNode(ExprNode):
    value: Any
    type_name: TypeName

@dataclass
class VarUsageNode(ExprNode):
    name: str

# ==========================================
#                 PARSER
# ==========================================

class ASTBuilder(Interpreter):
    def start(self, tree):
        return self.visit(tree.children[0])

    def program(self, tree):
        # program: memory_block code_block
        memory_block = self.visit(tree.children[0])
        code_block = self.visit(tree.children[1])
        return ProgramNode(memory_block=memory_block, task_list=code_block)

    def memory_block(self, tree):
        # memory_block: "memory:" decls "end_memory"
        return self.visit(tree.children[0])

    def decls(self, tree):
        # decls: declaration ";" decls | empty
        declarations = []
        for child in tree.children:
            res = self.visit(child)
            if isinstance(res, VarDeclNode):
                declarations.append(res)
            elif isinstance(res, list):
                declarations.extend(res)
        return declarations

    def declaration(self, tree):
        # declaration: "keep" CNAME "as" type_name
        cname = str(tree.children[0])
        type_name = self.visit(tree.children[1])
        return VarDeclNode(name=cname, type_name=type_name)

    def type_whole(self, tree): return TypeName.WHOLE
    def type_fract(self, tree): return TypeName.FRACT
    def type_quote(self, tree): return TypeName.QUOTE
    def type_flag(self, tree): return TypeName.FLAG

    def code_block(self, tree):
        # code_block: task_list
        return self.visit(tree.children[0])

    def task_list(self, tree):
        tasks = []
        for child in tree.children:
            res = self.visit(child)
            if isinstance(res, TaskNode):
                tasks.append(res)
            elif isinstance(res, list):
                tasks.extend(res)
        return tasks

    def task(self, tree):
        # task: "task" CNAME "[" params "]" "->" type_name ":" body "done"
        name = str(tree.children[0])
        params = self.visit(tree.children[1])
        return_type = self.visit(tree.children[2])
        body = self.visit(tree.children[3])
        return TaskNode(name=name, params=params, return_type=return_type, body=body)

    def params(self, tree):
        # params: param_list | empty
        if not tree.children:
            return []
        return self.visit(tree.children[0])

    def param_list(self, tree):
        # param_list: CNAME "as" type_name "," param_list | CNAME "as" type_name
        # Flattener
        res = []
        cname = str(tree.children[0])
        tname = self.visit(tree.children[1])
        res.append(VarDeclNode(name=cname, type_name=tname))
        if len(tree.children) > 2:
            res.extend(self.visit(tree.children[2]))
        return res

    def body(self, tree):
        # body: stat ";" body | empty
        stmts = []
        for child in tree.children:
            res = self.visit(child)
            if isinstance(res, StatNode):
                stmts.append(res)
            elif isinstance(res, BodyNode):
                stmts.extend(res.statements) # Flatten recursive body calls if any
            elif isinstance(res, list): # From recursion
                stmts.extend(res)
        return BodyNode(statements=stmts)

    def stat(self, tree):
        return self.visit(tree.children[0])

    def assignment(self, tree):
        # assignment: CNAME "<<" expr
        target = str(tree.children[0])
        expr = self.visit(tree.children[1])
        return AssignmentNode(target=target, expr=expr)

    def task_call_stat(self, tree):
        # task_call_stat: CNAME "run" "[" exprs "]"
        name = str(tree.children[0])
        args = self.visit(tree.children[1])
        return TaskCallStatNode(task_name=name, args=args)

    def yield_stat(self, tree):
        expr = self.visit(tree.children[0])
        return YieldNode(expr=expr)

    def show_stat(self, tree):
        return ShowNode(expr=self.visit(tree.children[0]))

    def grab_stat(self, tree):
        return GrabNode(target=str(tree.children[0]))

    def check_stat(self, tree):
        # check_stat: "check" expr "then" body elif_block else_block "close"
        cond = self.visit(tree.children[0])
        then_b = self.visit(tree.children[1])
        elif_b = self.visit(tree.children[2])
        else_b = self.visit(tree.children[3]) # Returns BodyNode or None
        return CheckNode(condition=cond, then_body=then_b, elif_blocks=elif_b, else_body=else_b)

    def elif_block(self, tree):
        # elif_block: "alt_check" expr "then" body elif_block | empty
        if not tree.children:
            return []
        cond = self.visit(tree.children[0])
        body = self.visit(tree.children[1])
        rest = self.visit(tree.children[2])
        return [ElifNode(condition=cond, body=body)] + rest

    def else_block(self, tree):
        # else_block: "alt" body | empty
        if not tree.children:
            return None
        return self.visit(tree.children[0])

    def loop_stat(self, tree):
        cond = self.visit(tree.children[0])
        body = self.visit(tree.children[1])
        return LoopNode(condition=cond, body=body)

    def exprs(self, tree):
        # exprs: expr "," exprs | expr | empty
        if not tree.children: return []
        head = self.visit(tree.children[0])
        if len(tree.children) > 1:
            tail = self.visit(tree.children[1])
            return [head] + tail
        return [head]

    def expr(self, tree):
         return self.visit(tree.children[0])

    def or_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='or', right=self.visit(tree.children[1]))
    def and_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='and', right=self.visit(tree.children[1]))
    def not_op(self, tree):
        return UnaryOpNode(op='not', expr=self.visit(tree.children[0]))

    def eq_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='is', right=self.visit(tree.children[1]))
    def neq_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='is_not', right=self.visit(tree.children[1]))
    def gt_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='over', right=self.visit(tree.children[1]))
    def lt_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='under', right=self.visit(tree.children[1]))

    def add_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='plus', right=self.visit(tree.children[1]))
    def sub_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='minus', right=self.visit(tree.children[1]))
    def mul_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='times', right=self.visit(tree.children[1]))
    def div_op(self, tree):
        return BinaryOpNode(left=self.visit(tree.children[0]), op='div', right=self.visit(tree.children[1]))

    def task_call_expr(self, tree):
        name = str(tree.children[0])
        args = self.visit(tree.children[1])
        return TaskCallExprNode(task_name=name, args=args)

    def var_usage(self, tree):
        return VarUsageNode(name=str(tree.children[0]))

    def const_whole(self, tree):
        return AtomNode(value=int(tree.children[0]), type_name=TypeName.WHOLE)
    def const_fract(self, tree):
        return AtomNode(value=float(tree.children[0]), type_name=TypeName.FRACT)
    def const_quote(self, tree):
        # Remove quotes
        s = str(tree.children[0])
        return AtomNode(value=s[1:-1], type_name=TypeName.QUOTE)
    def const_true(self, tree):
        return AtomNode(value=True, type_name=TypeName.FLAG)
    def const_false(self, tree):
        return AtomNode(value=False, type_name=TypeName.FLAG)


class ToyParser:
    def __init__(self, grammar_path="grammar.lark"):
        # Resolve absolute path if needed, or assume relative to caller
        if not os.path.exists(grammar_path):
             # Try to find it in the same directory as this file
             current_dir = os.path.dirname(os.path.abspath(__file__))
             grammar_path = os.path.join(current_dir, grammar_path)
             
        with open(grammar_path, 'r') as f:
            self.grammar = f.read()
        self.lark = Lark(self.grammar, start='start', parser='lalr')
        self.builder = ASTBuilder()

    def parse(self, text: str) -> ProgramNode:
        tree = self.lark.parse(text)
        return self.builder.visit(tree)


# ==========================================
#              EXECUTOR
# ==========================================

class ToyExecutor:
    def __init__(self, script: Optional[str] = None, testing_mode: bool = False):
        self.testing_mode = testing_mode
        self.global_memory: Dict[str, Any] = {}
        self.symbol_table_types: Dict[str, TypeName] = {}
        self.tasks: Dict[str, TaskNode] = {}
        if script:
            self.load_script(script)

    def load_script(self, script: str):
        parser = ToyParser()
        ast = parser.parse(script)
        self.execute(ast)

    def execute(self, ast: ProgramNode):
        # 1. Initialize Memory
        for decl in ast.memory_block:
            if decl.name in self.global_memory:
                 raise RuntimeError(f"Duplicate global variable: {decl.name}")
            self.symbol_table_types[decl.name] = decl.type_name
            # Initialize with default values
            if decl.type_name == TypeName.WHOLE: self.global_memory[decl.name] = 0
            elif decl.type_name == TypeName.FRACT: self.global_memory[decl.name] = 0.0
            elif decl.type_name == TypeName.QUOTE: self.global_memory[decl.name] = ""
            elif decl.type_name == TypeName.FLAG: self.global_memory[decl.name] = False

        # 2. Register Tasks
        for task in ast.task_list:
            if task.name in self.tasks:
                raise RuntimeError(f"Duplicate task: {task.name}")
            self.tasks[task.name] = task

        # 3. Find Entrypoint
        if "entrypoint" not in self.tasks:
            raise RuntimeError("No 'entrypoint' task found!")
        
        # 4. Run Entrypoint
        self.run_task("entrypoint", [])

    def run_task(self, task_name: str, args: List[Any], depth=0):
        if depth > 1000: raise RuntimeError("Stack overflow!")
        if task_name not in self.tasks:
             raise RuntimeError(f"Task not found: {task_name}")
        
        task = self.tasks[task_name]
        if len(args) != len(task.params):
            raise RuntimeError(f"Task {task_name} expects {len(task.params)} args, got {len(args)}")

        # Parameter binding with full type checking
        local_scope = {}
        local_scope_types = {}  # Track parameter types for grab
        for param, val in zip(task.params, args):
             # Type check for all types
             if param.type_name == TypeName.WHOLE and not isinstance(val, int):
                 raise RuntimeError(f"Type mismatch param {param.name}: expected WHOLE")
             if param.type_name == TypeName.FRACT and not isinstance(val, (int, float)):
                 raise RuntimeError(f"Type mismatch param {param.name}: expected FRACT")
             if param.type_name == TypeName.QUOTE and not isinstance(val, str):
                 raise RuntimeError(f"Type mismatch param {param.name}: expected QUOTE")
             if param.type_name == TypeName.FLAG and not isinstance(val, bool):
                 raise RuntimeError(f"Type mismatch param {param.name}: expected FLAG")
             local_scope[param.name] = val
             local_scope_types[param.name] = param.type_name
        
        return self.execute_body(task.body, local_scope, local_scope_types, depth)

    def execute_body(self, body: BodyNode, scope: Dict[str, Any], scope_types: Dict[str, TypeName] = None, depth: int = 0):
        if scope_types is None:
            scope_types = {}
        for stat in body.statements:
            res = self.execute_stat(stat, scope, scope_types, depth)
            if res is not None:
                return res
        return None

    def execute_stat(self, stat: StatNode, scope: Dict[str, Any], scope_types: Dict[str, TypeName] = None, depth: int = 0):
        if scope_types is None:
            scope_types = {}
        if isinstance(stat, AssignmentNode):
            val = self.evaluate_expr(stat.expr, scope, depth)
            # Check if global or local (param)
            if stat.target in scope:
                 # Semantics allow modifying params? usually yes.
                 scope[stat.target] = val
            elif stat.target in self.global_memory:
                 # Type check
                 expected = self.symbol_table_types[stat.target]
                 self.check_type(val, expected)
                 self.global_memory[stat.target] = val
            else:
                 raise RuntimeError(f"Unknown variable assignment: {stat.target}")

        elif isinstance(stat, TaskCallStatNode):
            arg_vals = [self.evaluate_expr(a, scope, depth) for a in stat.args]
            self.run_task(stat.task_name, arg_vals, depth + 1)  # Propagate depth

        elif isinstance(stat, YieldNode):
             val = self.evaluate_expr(stat.expr, scope, depth)
             return val

        elif isinstance(stat, ShowNode):
             val = self.evaluate_expr(stat.expr, scope, depth)
             if self.testing_mode:
                 print(f"{val}")
             else:
                 print(f"OUTPUT: {val}")

        elif isinstance(stat, GrabNode):
             # Mock input
             prompt = f"INPUT ({stat.target}): " if not self.testing_mode else ""
             val_str = input(prompt)
             # Need to convert based on target type
             # Check declaration
             if stat.target in scope:
                 # Parameter - look up type from scope_types
                 t = scope_types.get(stat.target, TypeName.QUOTE)
                 if t == TypeName.WHOLE: val = int(val_str)
                 elif t == TypeName.FRACT: val = float(val_str)
                 elif t == TypeName.FLAG: val = (val_str.lower() == 'yes')
                 else: val = val_str
                 scope[stat.target] = val
             elif stat.target in self.global_memory:
                 t = self.symbol_table_types[stat.target]
                 if t == TypeName.WHOLE: val = int(val_str)
                 elif t == TypeName.FRACT: val = float(val_str)
                 elif t == TypeName.FLAG: val = (val_str.lower() == 'yes')
                 else: val = val_str
                 self.global_memory[stat.target] = val
             else:
                 raise RuntimeError(f"Unknown var {stat.target}")

        elif isinstance(stat, CheckNode):
             cond = self.evaluate_expr(stat.condition, scope, depth)
             if cond:  # Truthy check instead of `is True`
                 return self.execute_body(stat.then_body, scope, scope_types, depth)
             else:
                 # Elif
                 for elif_b in stat.elif_blocks:
                      if self.evaluate_expr(elif_b.condition, scope, depth):  # Truthy check
                           return self.execute_body(elif_b.body, scope, scope_types, depth)
                 # Else
                 if stat.else_body:
                      return self.execute_body(stat.else_body, scope, scope_types, depth)

        elif isinstance(stat, LoopNode):
             while self.evaluate_expr(stat.condition, scope, depth):  # Truthy check
                 res = self.execute_body(stat.body, scope, scope_types, depth)
                 if res: return res  # Handle return inside loop

    def evaluate_expr(self, expr: ExprNode, scope: Dict[str, Any], depth: int = 0) -> Any:
        if isinstance(expr, AtomNode):
            return expr.value
        elif isinstance(expr, VarUsageNode):
            if expr.name in scope: return scope[expr.name]
            if expr.name in self.global_memory: return self.global_memory[expr.name]
            raise RuntimeError(f"Undefined variable: {expr.name}")
        elif isinstance(expr, BinaryOpNode):
            l = self.evaluate_expr(expr.left, scope, depth)
            r = self.evaluate_expr(expr.right, scope, depth)
            if expr.op == 'plus': return l + r
            if expr.op == 'minus': return l - r
            if expr.op == 'times': return l * r
            if expr.op == 'div': 
                if isinstance(l, int) and isinstance(r, int):
                    return l // r
                return l / r
            if expr.op == 'is': return l == r
            if expr.op == 'is_not': return l != r
            if expr.op == 'over': return l > r
            if expr.op == 'under': return l < r
            if expr.op == 'and': return l and r
            if expr.op == 'or': return l or r
        elif isinstance(expr, UnaryOpNode):
            v = self.evaluate_expr(expr.expr, scope, depth)
            if expr.op == 'not': return not v
        elif isinstance(expr, TaskCallExprNode):
            args = [self.evaluate_expr(a, scope, depth) for a in expr.args]
            return self.run_task(expr.task_name, args, depth + 1)  # Propagate depth
        
        raise RuntimeError(f"Unknown expr: {expr}")

    def check_type(self, val, expected_type: TypeName):
        if expected_type == TypeName.WHOLE and not isinstance(val, int): raise RuntimeError("Type Error: Expected WHOLE")
        if expected_type == TypeName.FRACT and not isinstance(val, float): raise RuntimeError("Type Error: Expected FRACT")
        if expected_type == TypeName.FLAG and not isinstance(val, bool): raise RuntimeError("Type Error: Expected FLAG")
        if expected_type == TypeName.QUOTE and not isinstance(val, str): raise RuntimeError("Type Error: Expected QUOTE")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run script from file
        with open(sys.argv[1], 'r') as f:
            script_content = f.read()
            ToyExecutor(script_content)
