#!/usr/bin/env python3
"""Zuverlaessiger Rechner fuer die Mitarbeiter — als Bus-Werkzeug, nicht als Skill.

Sprachmodelle rechnen im Kopf, und das geht bei Geld und langen Zahlen schief.
Deshalb gibt es `rechnen` auf dem Firmen-Bus: immer da, fuer jeden, ohne dass
ein Skill geladen oder gefunden werden muss.

Warum kein Claude-Code-Skill: Skills liegen unter `.claude/`, und diese Pfade
sind gesondert geschuetzt — Agenten koennen dort anlegen, aber nicht aufraeumen
(geprueft: `rm` wird verweigert, eine `.claude/settings.json` wird ohne
Trust-Dialog ignoriert). Ein Werkzeug, das seine Mitarbeiter nicht pflegen
koennen, gehoert nicht dorthin.

Kein eval, nur geprueftes AST.

Rechnet intern mit Decimal, damit Geldbetraege exakt bleiben (0.1 + 0.2 == 0.3).
Trigonometrie/Logarithmen laufen ueber float und kommen als Decimal zurueck --
dort ist Exaktheit ohnehin nicht zu haben.
"""

import ast
import math
import sys
from decimal import ROUND_HALF_UP, Decimal, DivisionByZero, InvalidOperation, Overflow, getcontext

getcontext().prec = 28

# Exponenten daruber sprengen entweder den Decimal-Kontext oder die Laufzeit.
MAX_EXPONENT = 10000


def _via_float(fn):
    """math-Funktion auf Decimal anwenden: rein als float, raus als Decimal."""
    return lambda *args: Decimal(repr(fn(*(float(a) for a in args))))


def _log(x, base=None):
    if base is None:
        return Decimal(repr(math.log(float(x))))
    return Decimal(repr(math.log(float(x), float(base))))


def _round(x, digits=0):
    # HALF_UP statt Pythons HALF_EVEN: bei Preisen wird kaufmaennisch gerundet,
    # 11.065 EUR muessen 11.07 werden und nicht 11.06.
    d = int(digits)
    if d >= 0:
        return x.quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    step = Decimal(1).scaleb(-d)
    return (x / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


FUNCS = {
    "sqrt": lambda x: x.sqrt(),
    "exp": _via_float(math.exp),
    "log": _log,
    "log2": _via_float(math.log2),
    "log10": _via_float(math.log10),
    "sin": _via_float(math.sin),
    "cos": _via_float(math.cos),
    "tan": _via_float(math.tan),
    "asin": _via_float(math.asin),
    "acos": _via_float(math.acos),
    "atan": _via_float(math.atan),
    "floor": lambda x: Decimal(math.floor(x)),
    "ceil": lambda x: Decimal(math.ceil(x)),
    "round": _round,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": lambda *a: sum(a, Decimal(0)),
}

CONSTS = {
    "pi": Decimal(repr(math.pi)),
    "e": Decimal(repr(math.e)),
    "tau": Decimal(repr(math.tau)),
}

def _guard_zero(fn):
    """Decimal wirft bei // und % durch 0 nur InvalidOperation -- zu unklar."""
    def wrapped(a, b):
        if b == 0:
            raise DivisionByZero
        return fn(a, b)
    return wrapped


BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: _guard_zero(lambda a, b: a / b),
    ast.FloorDiv: _guard_zero(lambda a, b: a // b),
    ast.Mod: _guard_zero(lambda a, b: a % b),
}


class CalcError(Exception):
    pass


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError(f"Nur Zahlen erlaubt, nicht: {node.value!r}")
        # str() statt float(), sonst schleppt 0.1 seinen Binaerfehler mit rein.
        return Decimal(str(node.value))

    if isinstance(node, ast.Name):
        if node.id not in CONSTS:
            raise CalcError(f"Unbekannter Name: {node.id!r} (erlaubt: {', '.join(CONSTS)})")
        return CONSTS[node.id]

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +_eval(node.operand)
        raise CalcError("Operator nicht erlaubt")

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return _power(_eval(node.left), _eval(node.right))
        op = BINOPS.get(type(node.op))
        if op is None:
            raise CalcError(f"Operator nicht erlaubt: {type(node.op).__name__}")
        return op(_eval(node.left), _eval(node.right))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise CalcError("Nur einfache Funktionsaufrufe erlaubt")
        if node.keywords:
            raise CalcError("Keine Schluesselwort-Argumente erlaubt")
        fn = FUNCS.get(node.func.id)
        if fn is None:
            raise CalcError(f"Unbekannte Funktion: {node.func.id!r} (erlaubt: {', '.join(sorted(FUNCS))})")
        return fn(*(_eval(a) for a in node.args))

    raise CalcError(f"Nicht erlaubt: {type(node).__name__}")


def _power(base, exp):
    if abs(exp) > MAX_EXPONENT:
        raise CalcError(f"Exponent zu gross (max. {MAX_EXPONENT})")
    if base < 0 and exp != exp.to_integral_value():
        raise CalcError("Negative Basis mit gebrochenem Exponenten ergibt keine reelle Zahl")
    return base ** exp


def fmt(value):
    """Immer als Dezimalzahl, nie in E-Notation.

    Nachkommastellen bleiben stehen -- wer round(x, 2) schreibt, will 3.80
    sehen und nicht 3.8.
    """
    return format(value, "f")


def calculate(expression):
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise CalcError(f"Ungueltiger Ausdruck: {exc.msg}") from None
    try:
        result = _eval(tree)
    except (DivisionByZero, ZeroDivisionError):
        raise CalcError("Division durch Null") from None
    except InvalidOperation:
        raise CalcError("Ungueltige Rechenoperation (z. B. sqrt einer negativen Zahl)") from None
    except Overflow:
        # decimal.Overflow ist KEIN OverflowError -- ohne diesen Zweig kam ein
        # (10**9999)**9999 als Server-Fehler zurueck statt als Rechenfehler.
        raise CalcError("Ergebnis zu gross") from None
    except (ValueError, OverflowError) as exc:
        raise CalcError(f"Rechenfehler: {exc}") from None
    except TypeError as exc:
        raise CalcError(f"Falsche Argumente: {exc}") from None
    if not isinstance(result, Decimal):
        raise CalcError("Kein numerisches Ergebnis")
    return fmt(result)


def main(argv):
    if len(argv) != 2 or not argv[1].strip():
        print('Aufruf: python3 calc.py "19 * 1.19"', file=sys.stderr)
        return 2
    try:
        print(calculate(argv[1]))
    except CalcError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
