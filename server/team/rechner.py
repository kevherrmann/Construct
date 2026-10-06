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


def _L(de: str, en: str) -> str:
    # Die Fehlermeldung geht an den Mitarbeiter, also in der Sprache der Installation.
    # Ohne Server (als Skript aufgerufen) bleibt es Deutsch.
    try:
        from server import config as cfg
    except ImportError:
        return de
    return cfg.L(de, en)


class CalcError(Exception):
    pass


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalcError(_L(f"Nur Zahlen erlaubt, nicht: {node.value!r}",
                               f"Only numbers allowed, not: {node.value!r}"))
        # str() statt float(), sonst schleppt 0.1 seinen Binaerfehler mit rein.
        return Decimal(str(node.value))

    if isinstance(node, ast.Name):
        if node.id not in CONSTS:
            raise CalcError(_L(f"Unbekannter Name: {node.id!r} (erlaubt: {', '.join(CONSTS)})",
                               f"Unknown name: {node.id!r} (allowed: {', '.join(CONSTS)})"))
        return CONSTS[node.id]

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +_eval(node.operand)
        raise CalcError(_L("Operator nicht erlaubt",
                           "Operator not allowed"))

    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return _power(_eval(node.left), _eval(node.right))
        op = BINOPS.get(type(node.op))
        if op is None:
            raise CalcError(_L(f"Operator nicht erlaubt: {type(node.op).__name__}",
                               f"Operator not allowed: {type(node.op).__name__}"))
        return op(_eval(node.left), _eval(node.right))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise CalcError(_L("Nur einfache Funktionsaufrufe erlaubt",
                               "Only simple function calls allowed"))
        if node.keywords:
            raise CalcError(_L("Keine Schluesselwort-Argumente erlaubt",
                               "No keyword arguments allowed"))
        fn = FUNCS.get(node.func.id)
        if fn is None:
            raise CalcError(_L(f"Unbekannte Funktion: {node.func.id!r} (erlaubt: {', '.join(sorted(FUNCS))})",
                               f"Unknown function: {node.func.id!r} (allowed: {', '.join(sorted(FUNCS))})"))
        return fn(*(_eval(a) for a in node.args))

    raise CalcError(_L(f"Nicht erlaubt: {type(node).__name__}",
                       f"Not allowed: {type(node).__name__}"))


def _power(base, exp):
    if abs(exp) > MAX_EXPONENT:
        raise CalcError(_L(f"Exponent zu gross (max. {MAX_EXPONENT})",
                           f"Exponent too large (max. {MAX_EXPONENT})"))
    if base < 0 and exp != exp.to_integral_value():
        raise CalcError(_L("Negative Basis mit gebrochenem Exponenten ergibt keine reelle Zahl",
                           "Negative base with a fractional exponent gives no real number"))
    return base ** exp


def fmt(value):
    """Immer als Dezimalzahl, nie in E-Notation.

    Nachkommastellen bleiben stehen -- wer round(x, 2) schreibt, will 3.80
    sehen und nicht 3.8.
    """
    return format(value, "f")


MAX_LAENGE = 2000


def calculate(expression):
    # Absurd tief verschachtelte Ausdruecke ("("*5000) sprengten Parser oder
    # _eval mit RecursionError/MemoryError -- am Bus ein 500 statt einer Antwort.
    if len(expression) > MAX_LAENGE:
        raise CalcError(_L(f"Ausdruck zu lang (max. {MAX_LAENGE} Zeichen)",
                           f"Expression too long (max. {MAX_LAENGE} characters)"))
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise CalcError(_L(f"Ungueltiger Ausdruck: {exc.msg}",
                           f"Invalid expression: {exc.msg}")) from None
    except (RecursionError, MemoryError):
        raise CalcError(_L("Ausdruck zu tief verschachtelt",
                           "Expression nested too deeply")) from None
    try:
        result = _eval(tree)
    except (DivisionByZero, ZeroDivisionError):
        raise CalcError(_L("Division durch Null",
                           "Division by zero")) from None
    except InvalidOperation:
        raise CalcError(_L("Ungueltige Rechenoperation (z. B. sqrt einer negativen Zahl)",
                           "Invalid operation (e.g. sqrt of a negative number)")) from None
    except Overflow:
        # decimal.Overflow ist KEIN OverflowError -- ohne diesen Zweig kam ein
        # (10**9999)**9999 als Server-Fehler zurueck statt als Rechenfehler.
        raise CalcError(_L("Ergebnis zu gross",
                           "Result too large")) from None
    except (ValueError, OverflowError) as exc:
        raise CalcError(_L(f"Rechenfehler: {exc}",
                           f"Calculation error: {exc}")) from None
    except TypeError as exc:
        raise CalcError(_L(f"Falsche Argumente: {exc}",
                           f"Wrong arguments: {exc}")) from None
    except (RecursionError, MemoryError):
        raise CalcError(_L("Ausdruck zu tief verschachtelt",
                           "Expression nested too deeply")) from None
    if not isinstance(result, Decimal):
        raise CalcError(_L("Kein numerisches Ergebnis",
                           "No numeric result"))
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
