"""Bazar AST classes and the stable text dump used by --ast.

Nodes retain their originating token's 1-based line and UTF-8 byte column.
The dump prints one node per line, indented by two spaces per level:

    NodeName line=L column=C field=value ...
      label:
        ChildNode ...

Scalar fields have a fixed order. Children appear under initializer, value,
condition, then_body, else_body, left, right, and operand labels. A missing
else branch prints as else_body: None. Program and block statements appear
in source order directly beneath their parent.
"""

from __future__ import annotations

from dataclasses import dataclass

INDENT = "  "


@dataclass
class ASTNode:
    line: int
    column: int

    def attributes(self):
        """Scalar fields on the node line, in dump order."""
        return ()

    def labelled_children(self):
        """Pairs of child labels and nodes (or None), in dump order."""
        return ()

    def statement_children(self):
        """Unlabelled child statements belonging to programs and blocks."""
        return ()

    def header(self):
        text = f"{type(self).__name__} line={self.line} column={self.column}"
        for name, value in self.attributes():
            text += f" {name}={value}"
        return text

    def dump(self):
        """Dump the entire subtree without a final newline."""
        return "\n".join(self.dump_lines())

    def dump_lines(self):
        """Yield dump lines one at a time, without line endings.

        An explicit stack replaces recursion, so long left-associative chains
        such as 1 плюс 1 плюс ... плюс 1 do not exhaust the Python stack.
        Yielding lines lets callers stream deep dumps instead of holding the
        whole text in memory.
        """
        stack = [(0, None, self)]  # (depth, label or None, node or None)
        while stack:
            depth, label, node = stack.pop()
            if label is not None:
                if node is None:
                    yield f"{INDENT * depth}{label}: None"
                    continue
                yield f"{INDENT * depth}{label}:"
                depth += 1
            yield INDENT * depth + node.header()
            pending = [(depth + 1, child_label, child)
                       for child_label, child in node.labelled_children()]
            pending += [(depth + 1, None, statement)
                        for statement in node.statement_children()]
            stack.extend(reversed(pending))


def _flag(value):
    return "true" if value else "false"


# ------------------------------------------------------------- program

@dataclass
class StmtNode(ASTNode):
    """Base class for all statements."""


@dataclass
class ExprNode(ASTNode):
    """Base class for all expressions."""


@dataclass
class ProgramNode(ASTNode):
    """Position: first non-NEWLINE token, or EOF for empty input."""
    statements: list[StmtNode]

    def statement_children(self):
        return self.statements


@dataclass
class BlockNode(ASTNode):
    """If/else branch body; positioned at its first statement."""
    statements: list[StmtNode]

    def statement_children(self):
        return self.statements


# ----------------------------------------------------------- statements

@dataclass
class DeclarationNode(StmtNode):
    """Immutable зуб даю (mutable=false) or mutable мутна тєма (mutable=true)."""
    name: str
    declared_type: str  # canonical: "i32", "i64", or "bool"
    mutable: bool
    initializer: ExprNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type),
                ("mutable", _flag(self.mutable)))

    def labelled_children(self):
        return (("initializer", self.initializer),)


@dataclass
class ConstantDeclarationNode(StmtNode):
    """Compile-time constant: желєзобетонно NAME тіпа TYPE це EXPR (top level only)."""
    name: str
    declared_type: str  # canonical: "i32", "i64", or "bool"
    initializer: ExprNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type))

    def labelled_children(self):
        return (("initializer", self.initializer),)


@dataclass
class AssignmentNode(StmtNode):
    """Assignment syntax: перевзувся NAME тепер EXPR."""
    name: str
    value: ExprNode

    def attributes(self):
        return (("name", self.name),)

    def labelled_children(self):
        return (("value", self.value),)


@dataclass
class IfNode(StmtNode):
    """Condition syntax: якшо реально ... [а нє ...] отакої."""
    condition: ExprNode
    then_body: BlockNode
    else_body: BlockNode | None

    def labelled_children(self):
        return (("condition", self.condition), ("then_body", self.then_body),
                ("else_body", self.else_body))


@dataclass
class PrintNode(StmtNode):
    """Output syntax: базарь EXPR."""
    value: ExprNode

    def labelled_children(self):
        return (("value", self.value),)


@dataclass
class ExitNode(StmtNode):
    """Exit syntax: всьо розходимось EXPR."""
    value: ExprNode

    def labelled_children(self):
        return (("value", self.value),)


# ---------------------------------------------------------- expressions

@dataclass
class IntegerNode(ExprNode):
    """Unsigned decimal literal.

    The value is a digit string without leading zeros (0 for zero).
    Keeping it as text permits arbitrary-length literals; range checking
    belongs to semantic analysis.
    """
    value: str

    def attributes(self):
        return (("value", self.value),)


@dataclass
class BooleanNode(ExprNode):
    """Boolean literals: реально (true) or гон (false)."""
    value: bool

    def attributes(self):
        return (("value", _flag(self.value)),)


@dataclass
class IdentifierNode(ExprNode):
    name: str

    def attributes(self):
        return (("name", self.name),)


@dataclass
class UnaryNode(ExprNode):
    """Unary syntax: мінус EXPR; operator is always neg."""
    operator: str
    operand: ExprNode

    def attributes(self):
        return (("operator", self.operator),)

    def labelled_children(self):
        return (("operand", self.operand),)


@dataclass
class BinaryNode(ExprNode):
    """Operator is one of add sub mul div eq ne gt lt and or."""
    operator: str
    left: ExprNode
    right: ExprNode

    def attributes(self):
        return (("operator", self.operator),)

    def labelled_children(self):
        return (("left", self.left), ("right", self.right))
