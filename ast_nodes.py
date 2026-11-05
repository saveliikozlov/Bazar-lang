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

Stage 2 adds list labels (parameters, fields, methods, arguments): each
item is printed one level below the label, and an empty list prints as
label: []. Types print as i32, i64, bool, or the structure name; an array
type prints as [ELEMENT; SIZE], with its size as written in the source,
може T as Option<T>, and вийде T або облом E as Result<T, E>.
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
                if isinstance(node, list):
                    if not node:
                        yield f"{INDENT * depth}{label}: []"
                        continue
                    yield f"{INDENT * depth}{label}:"
                    stack.extend((depth + 1, None, item) for item in reversed(node))
                    continue
                yield f"{INDENT * depth}{label}:"
                depth += 1
            yield INDENT * depth + node.header()
            pending = [(depth + 1, child_label, child)
                       for child_label, child in node.labelled_children()]
            pending += [(depth + 1, None, statement)
                        for statement in node.statement_children()]
            stack.extend(reversed(pending))


def children(node):
    """The direct child nodes of a node, whatever its class."""
    for value in vars(node).values():
        if isinstance(value, ASTNode):
            yield value
        elif isinstance(value, list):
            yield from (item for item in value if isinstance(item, ASTNode))


def walk(node):
    """The node and everything below it."""
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        stack.extend(children(current))


def _flag(value):
    return "true" if value else "false"


def _quote(text):
    """Show a string literal value with its escapes, as it is written in source."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


# --------------------------------------------------------------- types

@dataclass
class TypeNode(ASTNode):
    """Base class for a type as written in the source, positioned at its first token.

    It prints on its owner's line as an attribute (type=i32), never as a child
    node. The semantic pass turns it into a bazar_types.Type."""


@dataclass
class NamedTypeNode(TypeNode):
    """A type named by one word: i32, i64, bool (canonical), or a structure name."""
    name: str

    def __str__(self):
        return self.name


@dataclass
class ArrayTypeNode(TypeNode):
    """[ELEMENT; SIZE]: SIZE is a constant expression; size_text is its source spelling."""
    element: TypeNode
    size: ExprNode
    size_text: str

    def __str__(self):
        return f"[{self.element}; {self.size_text}]"


@dataclass
class OptionTypeNode(TypeNode):
    """може TYPE: a value of TYPE or none."""
    inner: TypeNode

    def __str__(self):
        return f"Option<{self.inner}>"


@dataclass
class ResultTypeNode(TypeNode):
    """вийде TYPE або облом TYPE: a result or an error."""
    ok: TypeNode
    error: TypeNode

    def __str__(self):
        return f"Result<{self.ok}, {self.error}>"


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
    declared_type: TypeNode
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
    declared_type: TypeNode
    initializer: ExprNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type))

    def labelled_children(self):
        return (("initializer", self.initializer),)


@dataclass
class AssignmentNode(StmtNode):
    """Assignment to a variable: перевзувся NAME тепер EXPR."""
    name: str
    value: ExprNode

    def attributes(self):
        return (("name", self.name),)

    def labelled_children(self):
        return (("value", self.value),)


@dataclass
class FieldAssignmentNode(StmtNode):
    """Assignment to a field or an element: перевзувся NAME.FIELD[INDEX]... тепер EXPR.

    The target is a chain of FieldAccessNode and IndexNode whose innermost
    object is an IdentifierNode; only its indexes may contain calls."""
    target: ExprNode
    value: ExprNode

    def labelled_children(self):
        return (("target", self.target), ("value", self.value))


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
class WhileNode(StmtNode):
    """Loop syntax: крутимось поки EXPR ... докрутились."""
    condition: ExprNode
    body: BlockNode

    def labelled_children(self):
        return (("condition", self.condition), ("body", self.body))


@dataclass
class ForNode(StmtNode):
    """Range loop syntax: крутимось NAME тіпа TYPE від EXPR по EXPR ... докрутились."""
    name: str
    declared_type: TypeNode
    start: ExprNode
    end: ExprNode
    body: BlockNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type))

    def labelled_children(self):
        return (("start", self.start), ("end", self.end), ("body", self.body))


@dataclass
class ForEachNode(StmtNode):
    """Array loop syntax: крутимось NAME тіпа TYPE з EXPR ... докрутились."""
    name: str
    declared_type: TypeNode
    array: ExprNode
    body: BlockNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type))

    def labelled_children(self):
        return (("array", self.array), ("body", self.body))


@dataclass
class BreakNode(StmtNode):
    """Leave the innermost loop: харе."""


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


@dataclass
class ReturnNode(StmtNode):
    """Return syntax: тримай EXPR (inside a function body)."""
    value: ExprNode

    def labelled_children(self):
        return (("value", self.value),)


@dataclass
class CallStatementNode(StmtNode):
    """A call on its own line; call is a CallNode or a MemberCallNode."""
    call: ExprNode

    def attributes(self):
        return (("member_call", _flag(isinstance(self.call, MemberCallNode))),)

    def labelled_children(self):
        return (("call", self.call),)


# ------------------------------------------------- functions and structures

@dataclass
class ParameterNode(ASTNode):
    """One parameter: NAME тіпа TYPE."""
    name: str
    declared_type: TypeNode

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type))


@dataclass
class FunctionNode(StmtNode):
    """маю дєло NAME(PARAMETERS) на виході TYPE ... порішали.

    At the top level it is a function; inside такі діла, a member function."""
    name: str
    parameters: list[ParameterNode]
    result_type: TypeNode
    body: BlockNode

    def attributes(self):
        return (("name", self.name), ("result", self.result_type))

    def labelled_children(self):
        return (("parameters", self.parameters), ("body", self.body))


@dataclass
class FieldNode(ASTNode):
    """A field: зуб даю NAME тіпа TYPE (constant) or мутна тєма ... (mutable).

    index is the position among the structure's fields, counting from 0.
    default is the constant expression after це, or None (auto constructor)."""
    name: str
    declared_type: TypeNode
    mutable: bool
    index: int
    default: ExprNode | None = None

    def attributes(self):
        return (("name", self.name), ("type", self.declared_type),
                ("mutable", _flag(self.mutable)), ("index", self.index))

    def labelled_children(self):
        return (("default", self.default),)


@dataclass
class StructureNode(StmtNode):
    """такі діла NAME ... порішали: fields and member functions in source order each."""
    name: str
    fields: list[FieldNode]
    methods: list[FunctionNode]

    def attributes(self):
        return (("name", self.name),)

    def labelled_children(self):
        return (("fields", self.fields), ("methods", self.methods))


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
class StringNode(ExprNode):
    """String literal; value has its escapes already resolved. Only базарь takes it."""
    value: str

    def attributes(self):
        return (("value", _quote(self.value)),)


@dataclass
class ReadNode(ExprNode):
    """ану кажи: reads one integer from standard input."""


@dataclass
class CallNode(ExprNode):
    """Call of a function by name: NAME(ARGUMENTS)."""
    name: str
    arguments: list[ExprNode]

    def attributes(self):
        return (("name", self.name),)

    def labelled_children(self):
        return (("arguments", self.arguments),)


@dataclass
class FieldAccessNode(ExprNode):
    """OBJECT.FIELD; positioned at the field name."""
    object: ExprNode
    field: str

    def attributes(self):
        return (("field", self.field),)

    def labelled_children(self):
        return (("object", self.object),)


@dataclass
class MemberCallNode(ExprNode):
    """OBJECT.METHOD(ARGUMENTS); positioned at the method name."""
    object: ExprNode
    method: str
    arguments: list[ExprNode]

    def attributes(self):
        return (("method", self.method),)

    def labelled_children(self):
        return (("object", self.object), ("arguments", self.arguments))


@dataclass
class NewObjectNode(ExprNode):
    """склепай STRUCTURE(ARGUMENTS): one argument per field, in field order."""
    structure: str
    arguments: list[ExprNode]

    def attributes(self):
        return (("structure", self.structure),)

    def labelled_children(self):
        return (("arguments", self.arguments),)


@dataclass
class IndexNode(ExprNode):
    """OBJECT[INDEX]: one element of an array; positioned at "["."""
    object: ExprNode
    index: ExprNode

    def labelled_children(self):
        return (("object", self.object), ("index", self.index))


@dataclass
class ArrayLiteralNode(ExprNode):
    """[EXPR, EXPR, ...]: an array of the listed elements, at least one."""
    elements: list[ExprNode]

    def labelled_children(self):
        return (("elements", self.elements),)


@dataclass
class ArrayFillNode(ExprNode):
    """[всюди EXPR]: every element is EXPR; the length comes from the expected type."""
    value: ExprNode

    def labelled_children(self):
        return (("value", self.value),)


@dataclass
class VariantNode(ExprNode):
    """шось(EXPR), нема, вийшло(EXPR), or облом(EXPR); variant is some, none, ok, or err.

    value is None for нема. Its type comes from context, except that шось(x)
    alone is може of the type of x."""
    variant: str
    value: ExprNode | None

    def attributes(self):
        return (("variant", self.variant),)

    def labelled_children(self):
        return () if self.value is None else (("value", self.value),)


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
