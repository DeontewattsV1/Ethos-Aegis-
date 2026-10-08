from __future__ import annotations

from dataclasses import dataclass


class Expr:
    pass


@dataclass(frozen=True)
class BoolConst(Expr):
    value: bool

    def __str__(self) -> str:
        return "T" if self.value else "F"


@dataclass(frozen=True)
class Symbol(Expr):
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Not(Expr):
    expr: Expr

    def __str__(self) -> str:
        return f"¬({self.expr})"


@dataclass(frozen=True)
class And(Expr):
    left: Expr
    right: Expr

    def __str__(self) -> str:
        return f"({self.left} ∧ {self.right})"


@dataclass(frozen=True)
class Or(Expr):
    left: Expr
    right: Expr

    def __str__(self) -> str:
        return f"({self.left} ∨ {self.right})"


T = BoolConst(True)
F = BoolConst(False)


def simplify(expr: Expr) -> Expr:
    if isinstance(expr, (BoolConst, Symbol)):
        return expr

    if isinstance(expr, Not):
        inner = simplify(expr.expr)
        if isinstance(inner, BoolConst):
            return BoolConst(not inner.value)
        if isinstance(inner, Not):
            return simplify(inner.expr)  # double negation
        if isinstance(inner, And):
            return simplify(Or(Not(inner.left), Not(inner.right)))  # De Morgan
        if isinstance(inner, Or):
            return simplify(And(Not(inner.left), Not(inner.right)))
        return Not(inner)

    if isinstance(expr, And):
        left = simplify(expr.left)
        right = simplify(expr.right)
        if left == right:
            return left  # idempotent
        if left == T:
            return right  # identity
        if right == T:
            return left
        if left == F or right == F:
            return F  # domination
        if isinstance(right, Or) and right.left == left:
            return left  # absorption
        if isinstance(left, Or) and left.left == right:
            return right
        return And(left, right)

    if isinstance(expr, Or):
        left = simplify(expr.left)
        right = simplify(expr.right)
        if left == right:
            return left
        if left == F:
            return right
        if right == F:
            return left
        if left == T or right == T:
            return T
        if isinstance(right, And) and right.left == left:
            return left
        if isinstance(left, And) and left.left == right:
            return right
        return Or(left, right)

    return expr
