"""Safe math calculator using AST evaluation — no eval()."""
import ast
import math
import operator

from plugins import jarvis_tool

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "pi": math.pi, "e": math.e, "tau": math.tau, "inf": math.inf,
    "sqrt": math.sqrt, "cbrt": lambda x: x ** (1 / 3),
    "sin": math.sin, "cos": math.cos, "tan": math.tan,
    "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log, "log2": math.log2, "log10": math.log10,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil,
    "degrees": math.degrees, "radians": math.radians,
    "factorial": math.factorial, "gcd": math.gcd,
}


def _eval_node(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported literal: {node.value!r}")
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only named function calls allowed")
        fn = _NAMES.get(node.func.id)
        if fn is None:
            raise ValueError(f"Unknown function: {node.func.id}")
        return fn(*[_eval_node(a) for a in node.args])
    if isinstance(node, ast.Name):
        val = _NAMES.get(node.id)
        if val is None:
            raise ValueError(f"Unknown name: {node.id}")
        return val
    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


@jarvis_tool(
    name="calculate",
    description=(
        "Evaluate a math expression safely. Supports +,-,*,/,**,%, "
        "sqrt, sin, cos, tan, log, log2, log10, exp, floor, ceil, factorial, pi, e."
    ),
    params={
        "expression": {
            "type": "string",
            "description": "Math expression, e.g. '2**10', 'sqrt(144)', 'sin(pi/2)'",
            "required": True,
        },
    },
)
def calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree)
        if isinstance(result, float) and result == int(result) and not math.isinf(result):
            result = int(result)
        return f"{expression} = {result}"
    except Exception as exc:
        return f"Calculation error: {exc}"
