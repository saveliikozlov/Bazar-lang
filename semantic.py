"""Bazar semantic analysis: a separate pass over the AST before code generation.

    analyze(program) -> ProgramInfo

The pass builds the symbol table (structures with their fields and member
functions, top-level functions, constants, and scoped variables), checks
every rule of README "Semantic rules", and annotates the AST for code
generation:

* every expression node gets .type: a bazar_types.Type (I32, I64, BOOL, or a
  StructType); a string literal printed by базарь gets STRING;
* IdentifierNode.ref, AssignmentNode.ref, DeclarationNode.info: a VarInfo
  or, inside a member function, a FieldInfo;
* CallNode.target / MemberCallNode.target: a FunctionInfo, and
  CallNode.on_self: a bare call of a member function on the own object;
* FieldAccessNode.field_info: the FieldInfo, whose index is the gep index;
  for розмір of an array it is None, and .length holds the length;
* IndexNode.index_value: the index when it is known now (and checked), or None;
* a check з.шось, з.нема, р.вийшло, р.облом is a FieldAccessNode whose
  field_info is None and whose .variant is some, none, ok, or err;
* BinaryNode.fallback: True for з або x, whose left side is може or вийде;
* every pattern of розбери gets .type, the type of the value it matches;
  BindingPatternNode.info is its VarInfo, and LiteralPatternNode.value the
  int or bool it compares with.
* ConstantDeclarationNode.info.value: the value computed at compile time.

The first error raises CompilationError with the position of the node that
broke the rule. Rule numbers in comments refer to the numbered list in
README section "Semantic rules".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ast_nodes import (
    ArrayFillNode, ArrayLiteralNode, ArrayTypeNode, AssignmentNode, BinaryNode, BindingPatternNode,
    BooleanNode, BreakNode, CallNode, CallStatementNode, ConstantDeclarationNode, DeclarationNode, ExitNode,
    FieldAccessNode, FieldAssignmentNode, ForEachNode, ForNode, FunctionNode, IdentifierNode, IfNode,
    IndexNode, IntegerNode, InterpolationNode, LiteralPatternNode, MatchNode, MemberCallNode, NewObjectNode,
    OptionTypeNode, OrPatternNode, PrintNode, ReadNode, ResultTypeNode, ReturnNode, StringNode, StructureNode,
    StructurePatternNode, TryNode, UnaryNode, VariantNode, VariantPatternNode, WhileNode, WildcardPatternNode,
)
from bazar_types import (
    BOOL, BUILTIN_TYPES, I32, I64, STRING, ArrayType, OptionType, ResultType, StructType, Type,
    byte_size, contained_structs, is_comparable, is_integer, is_scalar, is_variant,
)
from exhaustiveness import Alt, Con, Wild, show, useful
from parser import CompilationError

ARITHMETIC = ("add", "sub", "mul", "div")
LENGTH = "розмір"                    # the only field of an array
CHECKS = {"шось": "some", "нема": "none", "вийшло": "ok", "облом": "err"}   # з.шось and the others
MAX_ARRAY_LENGTH = 2**31 - 1
MAX_VALUE_BYTES = 2**40              # 1 TiB: no larger value fits a machine, and sizes stay far from 2**63
ORDERING = ("gt", "lt")
EQUALITY = ("eq", "ne")
LOGIC = ("and", "or")


def word(t):
    """A type as the programmer writes it."""
    return t.word


# ------------------------------------------------------------ symbol table

@dataclass(eq=False)
class VarInfo:
    """A constant, variable, parameter, or loop counter.

    kind: const, immutable, mutable, param, counter."""
    name: str
    type: Type
    kind: str
    value: object = None             # constants only: int or bool


@dataclass(eq=False)
class FieldInfo:
    name: str
    type: Type
    mutable: bool
    index: int
    node: object = None
    default: object = None           # the value after це: int or bool; None without one
    has_default: bool = False        # склепай may leave the field out (auto constructor)


@dataclass(eq=False)
class FunctionInfo:
    name: str
    parameters: list[VarInfo]
    result: Type
    node: FunctionNode
    owner: StructInfo | None = None  # the structure of a member function
    mutating: bool = False           # assigns a field of its own object (rule 23)
    assigns_field: bool = False      # directly, in its own body
    depends_on: set = field(default_factory=set)   # member functions whose mutation makes it mutating

    def describe(self):
        if self.owner:
            return f"«{self.owner.name}.{self.name}»"
        return f"«{self.name}»"


@dataclass(eq=False)
class StructInfo:
    name: str
    node: StructureNode
    fields: dict[str, FieldInfo] = field(default_factory=dict)      # in field order
    methods: dict[str, FunctionInfo] = field(default_factory=dict)


@dataclass
class ProgramInfo:
    structures: dict[str, StructInfo]
    functions: dict[str, FunctionInfo]
    constants: dict[str, VarInfo]


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}

    def lookup(self, name):
        scope = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None


@dataclass
class Context:
    """Where a body is checked: the main program, a function, or a member function."""
    function: FunctionInfo | None
    scope: Scope
    const_only: bool = False         # inside a желєзобетонно initializer or an array size
    in_loop: bool = False            # харе has a loop to leave
    const_of: str = "«желєзобетонно»"   # what const_only checks, for its messages

    @property
    def structure(self):
        return self.function.owner if self.function else None


@dataclass
class ChainStep:
    """The first step of a chain that is not mutable; name None means a temporary value."""
    line: int
    column: int
    name: str | None


@dataclass
class MemberCallSite:
    """A call of a member function on a chain, checked once mutating flags are final."""
    node: MemberCallNode
    target: FunctionInfo
    problem: ChainStep | None        # the first constant step of the object chain


def error(node, message):
    return CompilationError(node.line, node.column, message)


def count(number):
    """Ukrainian plural: 1 аргумент, 2 аргументи, 5 аргументів."""
    if number % 10 == 1 and number % 100 != 11:
        return f"{number} аргумент"
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return f"{number} аргументи"
    return f"{number} аргументів"


def literal_value(node):
    """The signed value of a literal with optional unary minuses, or None."""
    sign = 1
    while isinstance(node, UnaryNode):
        sign = -sign
        node = node.operand
    if isinstance(node, IntegerNode):
        return sign * int(node.value)
    return None


def is_flexible(node):
    """Literals and ану кажи take their integer type from context (rule 10, 15)."""
    if isinstance(node, (IntegerNode, ReadNode)):
        return True
    if isinstance(node, UnaryNode):
        return is_flexible(node.operand)
    if isinstance(node, BinaryNode) and node.operator in ARITHMETIC:
        return is_flexible(node.left) and is_flexible(node.right)
    if isinstance(node, ArrayLiteralNode):
        return all(is_flexible(item) for item in node.elements)
    return isinstance(node, (ArrayFillNode, VariantNode))


def needs_context(node):
    """An expression with no type of its own: [всюди x], нема, вийшло(x), облом(e)."""
    if isinstance(node, VariantNode):
        return node.variant != "some"
    return isinstance(node, ArrayFillNode)


def first_typed(nodes):
    """The operand to type first: one with a type of its own, else one that can infer it."""
    return (next((node for node in nodes if not is_flexible(node)), None)
            or next((node for node in nodes if not needs_context(node)), nodes[0]))


def simple(pattern):
    """A checked pattern in the shapes of exhaustiveness: Wild, Con, or Alt."""
    if isinstance(pattern, (WildcardPatternNode, BindingPatternNode)):
        return Wild()
    if isinstance(pattern, LiteralPatternNode):
        kind = "bool" if isinstance(pattern.value, bool) else "int"
        return Con((kind, pattern.value))
    if isinstance(pattern, VariantPatternNode):
        return Con((pattern.variant,), () if pattern.inner is None else (simple(pattern.inner),))
    if isinstance(pattern, StructurePatternNode):
        return Con(("struct", pattern.structure), tuple(simple(field) for field in pattern.fields))
    return Alt(tuple(simple(alternative) for alternative in pattern.alternatives))


def is_name_chain(node):
    """A name or its fields: reading it runs nothing and cannot fail."""
    while isinstance(node, FieldAccessNode):
        node = node.object
    return isinstance(node, IdentifierNode)


def constant_value(node):
    """The value of a checked integer expression known now, or None if it is unknown or overflows.

    Known are literals, integer constants, розмір of a name, and arithmetic on them."""
    if isinstance(node, IntegerNode):
        return int(node.value)
    if isinstance(node, IdentifierNode):
        known = isinstance(node.ref, VarInfo) and node.ref.kind == "const"
        return node.ref.value if known and is_integer(node.ref.type) else None
    if isinstance(node, FieldAccessNode):
        known = getattr(node, "length", None) is not None and is_name_chain(node.object)
        return node.length if known else None
    if isinstance(node, UnaryNode):
        operand = constant_value(node.operand)
        value = None if operand is None else -operand
    elif isinstance(node, BinaryNode) and node.operator in ARITHMETIC:
        left, right = constant_value(node.left), constant_value(node.right)
        if left is None or right is None or (node.operator == "div" and right == 0):
            return None
        if node.operator == "add":
            value = left + right
        elif node.operator == "sub":
            value = left - right
        elif node.operator == "mul":
            value = left * right
        else:
            quotient = abs(left) // abs(right)
            value = quotient if (left < 0) == (right < 0) else -quotient
    else:
        return None
    if value is None:
        return None
    low, high = node.type.range
    return value if low <= value <= high else None


def chain_root(node):
    while isinstance(node, (FieldAccessNode, MemberCallNode, IndexNode)):
        node = node.object
    return node


class Analyzer:
    def __init__(self):
        self.structures = {}
        self.functions = {}
        self.constants = {}
        self.member_calls = []
        self.sizes_pending = []          # (array type, its node) until every structure has its fields
        self.structures_complete = False

    # ---------------------------------------------------------- top level

    def analyze(self, program):
        statements = program.statements
        structures = [s for s in statements if isinstance(s, StructureNode)]
        functions = [s for s in statements if isinstance(s, FunctionNode)]
        # Rule 1: every declaration is collected before any body is checked.
        for node in structures:
            self.declare_structure(node)
        # Constants are computed in source order; function bodies see all of them.
        # They come before the signatures and fields, whose array sizes use them.
        constant_scope = Scope()
        for node in statements:
            if isinstance(node, ConstantDeclarationNode):
                self.declare_constant(node, constant_scope)
        for node in functions:
            self.declare_top_function(node)
        for node in structures:
            self.declare_members(self.structures[node.name])
        self.check_structure_cycles(structures)
        self.structures_complete = True
        for array_type, node in self.sizes_pending:
            self.check_size(array_type, node)
        for node in structures:
            self.check_defaults(self.structures[node.name], constant_scope)
        self.fill_auto_defaults()
        for node in statements:
            if isinstance(node, StructureNode):
                for method in self.structures[node.name].methods.values():
                    self.check_function(method)
            elif isinstance(node, FunctionNode):
                self.check_function(self.functions[node.name])
        self.check_main(statements)
        self.resolve_mutation()
        return ProgramInfo(self.structures, self.functions, self.constants)

    def declare_structure(self, node):
        if node.name in BUILTIN_TYPES:
            raise error(node, f"Назва «{node.name}» зайнята: так в AST пишуться вбудовані типи. "
                              f"Назви структуру інакше.")
        if node.name in self.structures:
            raise error(node, f"Структура «{node.name}» вже є. Дві «такі діла» з одним ім'ям не канають.")
        self.structures[node.name] = StructInfo(node.name, node)

    def declare_top_function(self, node):
        if node.name in self.functions:
            raise error(node, f"Функція «{node.name}» вже є. Дві «маю дєло» з одним ім'ям не канають.")
        if node.name in self.structures:
            raise error(node, f"«{node.name}» — вже назва структури, функцію так не назвеш.")
        self.functions[node.name] = self.function_info(node, None)

    def declare_members(self, structure):
        node = structure.node
        for field_node in node.fields:
            if field_node.name in structure.fields:
                raise error(field_node, f"Поле «{field_node.name}» в «{node.name}» вже є.")
            field_type = self.resolve_type(field_node.declared_type)
            structure.fields[field_node.name] = FieldInfo(
                field_node.name, field_type, field_node.mutable, field_node.index, field_node)
        for method in node.methods:
            if method.name in structure.methods:
                raise error(method, f"Функція «{method.name}» в «{node.name}» вже є.")
            if method.name in structure.fields:
                raise error(method, f"В «{node.name}» вже є поле «{method.name}», "
                                    f"функцію-член так не назвеш.")
            structure.methods[method.name] = self.function_info(method, structure)

    def function_info(self, node, owner):
        parameters = []
        for parameter in node.parameters:
            if any(p.name == parameter.name for p in parameters):
                raise error(parameter, f"Параметр «{parameter.name}» вже є в «{node.name}».")
            parameter_type = self.resolve_type(parameter.declared_type)
            parameters.append(VarInfo(parameter.name, parameter_type, "param"))
        result = self.resolve_type(node.result_type)
        return FunctionInfo(node.name, parameters, result, node, owner)

    def resolve_type(self, node, context=None):
        """The Type that a TypeNode names; an unknown structure name is an error at it.

        context is where the type is written, for the constants an array size
        may use; None is a signature or a field, which see every constant."""
        if isinstance(node, ArrayTypeNode):
            array_type = ArrayType(self.resolve_type(node.element, context), self.array_length(node.size, context))
            self.check_size(array_type, node)
            return array_type
        if isinstance(node, OptionTypeNode):
            return OptionType(self.resolve_type(node.inner, context))
        if isinstance(node, ResultTypeNode):
            return ResultType(self.resolve_type(node.ok, context), self.resolve_type(node.error, context))
        if node.name in BUILTIN_TYPES:
            return BUILTIN_TYPES[node.name]
        if node.name in self.structures:
            return StructType(node.name)
        raise error(node, f"Шо за тип «{node.name}»? Такої структури нема, а з вбудованих є "
                          f"«дрібняк», «крупняк» і «базар».")

    def array_length(self, node, context):
        """An array size: a constant integer expression from 1 to MAX_ARRAY_LENGTH."""
        scope = Scope()
        scope.names = self.visible_constants(context)
        self.require_integer(node, None, Context(None, scope, const_only=True, const_of="розмірі масиву"))
        length = self.evaluate(node)
        if not 1 <= length <= MAX_ARRAY_LENGTH:
            raise error(node, f"Розмір масиву має бути від 1 до {MAX_ARRAY_LENGTH}, а тут {length}.")
        return length

    def check_size(self, array_type, node):
        # Rule 33: a value of at most MAX_VALUE_BYTES; nested lengths multiply.
        if not self.structures_complete:
            self.sizes_pending.append((array_type, node))
            return
        size = byte_size(array_type, lambda name: [f.type for f in self.structures[name].fields.values()])
        if size > MAX_VALUE_BYTES:
            raise error(node, f"Масив «{word(array_type)}» завеликий: це {size} байтів, а одне значення "
                              f"в Базарі може мати до {MAX_VALUE_BYTES} байтів (1 ТіБ).")

    def visible_constants(self, context):
        """The constants a name in context refers to: rule 6, 7, 8 without the non-constants."""
        if context is None:
            names = dict(self.constants)
        else:
            names = {}
            if context.function is not None:
                names.update(self.constants)
                if context.structure is not None:
                    names.update(context.structure.fields)
            scopes = []
            scope = context.scope
            while scope is not None:
                scopes.append(scope)
                scope = scope.parent
            for scope in reversed(scopes):
                names.update(scope.names)
        return {name: info for name, info in names.items()
                if isinstance(info, VarInfo) and info.kind == "const"}

    def check_structure_cycles(self, structures):
        # Rule 16: an object cannot contain itself, directly or through fields.
        state = {}                           # name -> "visiting" | "done"

        def visit(structure):
            state[structure.name] = "visiting"
            for info in structure.fields.values():
                for name in contained_structs(info.type):
                    inner = self.structures[name]
                    if state.get(inner.name) == "visiting":
                        node = next(f for f in structure.node.fields if f.name == info.name)
                        raise error(node, f"Структура «{inner.name}» містить сама себе через поле "
                                          f"«{structure.name}.{info.name}»: такий об'єкт був би безкінечним.")
                    if inner.name not in state:
                        visit(inner)
            state[structure.name] = "done"

        for node in structures:
            if node.name not in state:
                visit(self.structures[node.name])

    # ---------------------------------------------------- auto constructor

    def check_defaults(self, structure, constants):
        """A default after це is a constant expression of the field's type.

        A structure-typed field has no це; it gets a default automatically
        when every field of its structure has one, recursively."""
        for info in structure.fields.values():
            node = info.node
            if node.default is None:
                continue
            if isinstance(info.type, ArrayType):
                raise error(node.default, f"Поле «{info.name}» — масив, йому «це» не пишуть: "
                                          f"значення масиву давай у «склепай».")
            if is_variant(info.type):
                raise error(node.default, f"Поле «{info.name}» — «{word(info.type)}», йому «це» не пишуть: "
                                          f"значення давай у «склепай».")
            if not is_scalar(info.type):
                raise error(node.default, f"Поле «{info.name}» — об'єкт «{info.type}», йому «це» не пишуть: "
                                          f"воно склепається саме, якщо всі поля «{info.type}» мають «це».")
            context = Context(None, constants, const_only=True)
            self.require(node.default, info.type, context)
            info.default = self.evaluate(node.default)
            info.has_default = True

    def fill_auto_defaults(self):
        # Structures may be declared in any order and contain each other, so
        # repeat until no field changes (there are no cycles, rule 16).
        changed = True
        while changed:
            changed = False
            for structure in self.structures.values():
                for info in structure.fields.values():
                    if not info.has_default and isinstance(info.type, StructType) and all(
                            f.has_default for f in self.structures[info.type.name].fields.values()):
                        info.has_default = changed = True

    # ----------------------------------------------------------- constants

    def declare_constant(self, node, scope):
        if node.name in scope.names:
            raise error(node, f"«{node.name}» вже оголошено. Двічі одне ім'я в одному місці не канає.")
        declared = self.resolve_type(node.declared_type)
        if not is_scalar(declared):
            raise error(node, "«Желєзобетонно» буває тільки «дрібняк», «крупняк» або «базар».")
        context = Context(None, scope, const_only=True)
        self.require(node.initializer, declared, context)
        value = self.evaluate(node.initializer)
        info = VarInfo(node.name, declared, "const", value)
        node.info = info
        scope.names[node.name] = info
        self.constants[node.name] = info

    def evaluate(self, node):
        """Compute a checked constant expression; arithmetic overflow is an error."""
        if isinstance(node, IntegerNode):
            return int(node.value)
        if isinstance(node, BooleanNode):
            return node.value
        if isinstance(node, IdentifierNode):
            return node.ref.value
        if isinstance(node, UnaryNode):
            return self.checked(node, -self.evaluate(node.operand))
        left = self.evaluate(node.left)
        if node.operator == "and":
            return left and self.evaluate(node.right)
        if node.operator == "or":
            return left or self.evaluate(node.right)
        right = self.evaluate(node.right)
        if node.operator == "add":
            return self.checked(node, left + right)
        if node.operator == "sub":
            return self.checked(node, left - right)
        if node.operator == "mul":
            return self.checked(node, left * right)
        if node.operator == "div":
            if right == 0:
                raise error(node, "Ділити на нуль? Навіть у желєзобетонно не вийде.")
            quotient = abs(left) // abs(right)
            return self.checked(node, quotient if (left < 0) == (right < 0) else -quotient)
        return {"eq": left == right, "ne": left != right,
                "gt": left > right, "lt": left < right}[node.operator]

    def checked(self, node, value):
        low, high = node.type.range
        if not low <= value <= high:
            raise error(node, f"Переповнення в желєзобетонно: {value} не влазить у «{word(node.type)}».")
        return value

    # -------------------------------------------------------------- bodies

    def check_function(self, function):
        scope = Scope()
        for parameter in function.parameters:
            scope.names[parameter.name] = parameter
        context = Context(function, scope)
        body = function.node.body
        self.check_statements(body.statements, context)
        if not self.always_returns(body.statements):
            raise error(function.node, f"Функція {function.describe()} може скінчитись без «тримай». "
                                       f"Кожен шлях має щось віддати.")

    def always_returns(self, statements):
        # Rule 13: the body ends with тримай, or with якшо … а нє … whose branches both do.
        last = statements[-1]
        if isinstance(last, ReturnNode):
            return True
        if isinstance(last, IfNode) and last.else_body is not None:
            return (self.always_returns(last.then_body.statements)
                    and self.always_returns(last.else_body.statements))
        if isinstance(last, MatchNode):
            # Rule 46: one arm always runs, so it is enough that every arm returns.
            return all(self.always_returns(arm.body.statements) for arm in last.arms)
        return False

    def check_main(self, statements):
        scope = Scope()
        context = Context(None, scope)
        for node in statements:
            if isinstance(node, ConstantDeclarationNode):
                # Rule 6: the main program sees a constant from its declaration on.
                if node.name in scope.names:
                    raise error(node, f"«{node.name}» вже оголошено. Двічі одне ім'я в одному місці не канає.")
                scope.names[node.name] = node.info
            elif not isinstance(node, (StructureNode, FunctionNode)):
                self.check_statement(node, context)

    def check_statements(self, statements, context):
        for index, node in enumerate(statements):
            if index and isinstance(statements[index - 1], ReturnNode):
                raise error(node, "Після «тримай» вже нічого не виконається: прибери цей рядок.")
            if index and isinstance(statements[index - 1], BreakNode):
                raise error(node, "Після «харе» вже нічого не виконається: прибери цей рядок.")
            self.check_statement(node, context)

    def check_block(self, block, context, in_loop=None):
        # A nested block stays inside the loop around it; a function body starts outside any loop.
        in_loop = context.in_loop if in_loop is None else in_loop
        inner = Context(context.function, Scope(context.scope), in_loop=in_loop)
        self.check_statements(block.statements, inner)

    def check_statement(self, node, context):
        if isinstance(node, DeclarationNode):
            self.check_declaration(node, context)
        elif isinstance(node, AssignmentNode):
            self.check_assignment(node, context)
        elif isinstance(node, FieldAssignmentNode):
            self.check_field_assignment(node, context)
        elif isinstance(node, PrintNode):
            if isinstance(node.value, StringNode):
                node.value.type = STRING
            elif isinstance(node.value, InterpolationNode):
                # Rule 48: every {…} part is an expression of any type, printed as базарь prints it.
                node.value.type = STRING
                for part in node.value.parts:
                    if isinstance(part, StringNode):
                        part.type = STRING
                    else:
                        self.expression(part, None, context)
            else:
                self.expression(node.value, None, context)
        elif isinstance(node, ExitNode):
            if context.function is not None:
                raise error(node, "«Всьо розходимось» — тільки в основній програмі. "
                                  "З функції виходять через «тримай».")
            self.require_integer(node.value, None, context)
        elif isinstance(node, ReturnNode):
            if context.function is None:
                raise error(node, "«Тримай» — тільки всередині «маю дєло». "
                                  "З програми виходять через «всьо розходимось».")
            self.require(node.value, context.function.result, context)
        elif isinstance(node, CallStatementNode):
            self.expression(node.call, None, context)
        elif isinstance(node, IfNode):
            self.require(node.condition, BOOL, context)
            self.check_block(node.then_body, context)
            if node.else_body is not None:
                self.check_block(node.else_body, context)
        elif isinstance(node, WhileNode):
            self.require(node.condition, BOOL, context)
            self.check_block(node.body, context, in_loop=True)
        elif isinstance(node, ForNode):
            self.check_for(node, context)
        elif isinstance(node, ForEachNode):
            self.check_for_each(node, context)
        elif isinstance(node, MatchNode):
            self.check_match(node, context)
        elif isinstance(node, BreakNode):
            if not context.in_loop:
                raise error(node, "«Харе» — тільки всередині «крутимось»: виходити нема з чого.")
        else:
            raise error(node, "Тут таке оголошувати не можна.")

    def check_for(self, node, context):
        # Rules 27, 28: the bounds are checked outside the counter's scope; the
        # counter and the outer block of the body are one scope.
        counter_type = self.resolve_type(node.declared_type, context)
        if not is_integer(counter_type):
            raise error(node.declared_type, f"Лічильник «{node.name}» має бути цілим числом, "
                                      f"а не «{word(counter_type)}».")
        self.require(node.start, counter_type, context)
        self.require(node.end, counter_type, context)
        info = VarInfo(node.name, counter_type, "counter")
        node.info = info
        scope = Scope(context.scope)
        scope.names[node.name] = info
        self.check_statements(node.body.statements, Context(context.function, scope, in_loop=True))

    def check_for_each(self, node, context):
        # Rule 38: the array is checked outside the counter's scope, and the counter
        # holds each element in turn; it has the element type and cannot be assigned.
        element_type = self.resolve_type(node.declared_type, context)
        if isinstance(node.array, ArrayLiteralNode):
            # The counter's type is the element type of a listed array: [1, 2] of дрібняк.
            array_type = self.expression(node.array, ArrayType(element_type, len(node.array.elements)), context)
        else:
            array_type = self.expression(node.array, None, context)
        if not isinstance(array_type, ArrayType):
            raise error(node.array, f"«Крутимось … з» ходить тільки по масиву, а тут «{word(array_type)}».")
        if array_type.element != element_type:
            raise error(node.declared_type, f"У масиві лежать «{word(array_type.element)}», а лічильник "
                                            f"«{node.name}» — «{word(element_type)}».")
        info = VarInfo(node.name, element_type, "counter")
        node.info = info
        scope = Scope(context.scope)
        scope.names[node.name] = info
        self.check_statements(node.body.statements, Context(context.function, scope, in_loop=True))

    def check_match(self, node, context):
        # Rule 43: the value is evaluated once; each arm is a child scope that
        # holds its names and the outer block of its body.
        subject_type = self.expression(node.subject, None, context)
        covered = []                     # one row per alternative of each arm without a guard
        for arm in node.arms:
            names = {}
            self.check_pattern(arm.pattern, subject_type, names, False, context)
            alternatives = arm.pattern.alternatives if isinstance(arm.pattern, OrPatternNode) else [arm.pattern]
            seen = list(covered)
            for alternative in alternatives:
                # Rule 45: an arm, or one alternative of it, that nothing can reach is an error.
                row = (simple(alternative),)
                if useful(seen, row, [subject_type], self.structures) is None:
                    what = "Цей варіант у «або»" if len(alternatives) > 1 else "Цей випадок"
                    raise error(alternative, f"{what} ніколи не спрацює: усе, шо він ловить, "
                                             f"уже розібрано вище.")
                seen.append(row)
            if arm.guard is None:
                covered.extend((simple(alternative),) for alternative in alternatives)
            scope = Scope(context.scope)
            scope.names.update(names)
            arm_context = Context(context.function, scope, in_loop=context.in_loop)
            if arm.guard is not None:
                self.require(arm.guard, BOOL, arm_context)
            self.check_statements(arm.body.statements, arm_context)
        # Rule 44: every value has an arm; an arm with a guard may not match, so it does not count.
        witness = useful(covered, (Wild(),), [subject_type], self.structures)
        if witness is not None:
            guarded = any(arm.guard is not None for arm in node.arms)
            note = (" Випадки з «якшо реально» не рахуються: їхня умова може не справдитись."
                    if guarded else "")
            raise error(node, f"Не всі випадки розібрано: шо робити з «{show(witness[0])}»? "
                              f"Додай для нього «випадок» або «випадок _».{note}")

    def check_pattern(self, node, t, names, in_alternatives, context):
        """Check a pattern against the type of the value it matches; collect the names it binds."""
        node.type = t
        if isinstance(node, WildcardPatternNode):
            return
        if isinstance(node, BindingPatternNode):
            if in_alternatives:
                raise error(node, f"У зразку з «або» імена не прив'язують: тут «{node.name}». "
                                  f"Пиши «_» або розбери варіанти окремими випадками.")
            if node.name in names:
                raise error(node, f"Ім'я «{node.name}» уже є в цьому зразку.")
            node.info = VarInfo(node.name, t, "immutable")
            names[node.name] = node.info
            return
        if isinstance(node, LiteralPatternNode):
            self.require(node.literal, t, context)
            literal = node.literal
            node.value = literal.value if isinstance(literal, BooleanNode) else literal_value(literal)
            return
        if isinstance(node, VariantPatternNode):
            option = node.variant in ("some", "none")
            if not isinstance(t, OptionType if option else ResultType):
                written = {"some": "шось(…)", "none": "нема", "ok": "вийшло(…)", "err": "облом(…)"}[node.variant]
                owner = "може" if option else "вийде"
                raise error(node, f"Зразок «{written}» — для «{owner}», а розбираємо «{word(t)}».")
            if node.inner is not None:
                inner = t.inner if option else (t.ok if node.variant == "ok" else t.error)
                self.check_pattern(node.inner, inner, names, in_alternatives, context)
            return
        if isinstance(node, StructurePatternNode):
            if node.structure not in self.structures:
                raise error(node, f"Шо за структура «{node.structure}»? Такої «такі діла» нема.")
            if t != StructType(node.structure):
                raise error(node, f"Зразок «{node.structure}(…)» — для «{node.structure}», "
                                  f"а розбираємо «{word(t)}».")
            fields = list(self.structures[node.structure].fields.values())
            if len(node.fields) != len(fields):
                raise error(node, f"У «{node.structure}» полів: {len(fields)}, а в зразку {len(node.fields)}. "
                                  f"Для поля, яке не цікавить, пиши «_».")
            for field_pattern, field_info in zip(node.fields, fields):
                self.check_pattern(field_pattern, field_info.type, names, in_alternatives, context)
            return
        for alternative in node.alternatives:       # OrPatternNode
            self.check_pattern(alternative, t, names, True, context)

    def check_declaration(self, node, context):
        declared = self.resolve_type(node.declared_type, context)
        # The initializer cannot see the name it declares: check it first.
        self.require(node.initializer, declared, context)
        if node.name in context.scope.names:
            raise error(node, f"«{node.name}» вже оголошено. Двічі одне ім'я в одному місці не канає.")
        info = VarInfo(node.name, declared, "mutable" if node.mutable else "immutable")
        node.info = info
        context.scope.names[node.name] = info

    def check_assignment(self, node, context):
        info = self.lookup_value(node.name, node, context)
        node.ref = info
        if isinstance(info, FieldInfo):
            # Rule 22: a member function assigning its own field.
            if not info.mutable:
                raise error(node, f"Поле «{info.name}» — «зуб даю», перевзуватись нема чого.")
            context.function.assigns_field = True
        elif info.kind == "param":
            raise error(node, f"«{info.name}» — параметр, його не перевзувають. "
                              f"Хочеш міняти — заведи «мутна тєма».")
        elif info.kind == "counter":
            raise error(node, f"«{info.name}» — лічильник циклу, він крутиться сам. "
                              f"Хочеш міняти — заведи «мутна тєма».")
        elif info.kind != "mutable":
            raise error(node, f"Ти за '{info.name}' зуб дав. Перевзуватись нема чого.")
        self.require(node.value, info.type, context)

    def check_field_assignment(self, node, context):
        target_type = self.expression(node.target, None, context)
        if isinstance(node.target, FieldAccessNode) and node.target.field_info is None:
            raise error(node.target, "«Розмір» масиву не перевзувають: він желєзобетонний.")
        problem = self.chain_problem(node.target, context)
        if problem:
            raise error(problem, f"Через «{problem.name}» не перевзуєшся: увесь ланцюжок має бути «мутна тєма».")
        if isinstance(chain_root(node.target).ref, FieldInfo):
            context.function.assigns_field = True
        self.require(node.value, target_type, context)

    def chain_problem(self, node, context):
        """Rule 21, 22, 24: the first constant step of a chain, or None if it is mutable throughout.

        The result is a ChainStep naming that step and positioned at it."""
        if isinstance(node, FieldAccessNode):
            problem = self.chain_problem(node.object, context)
            if problem:
                return problem
            return None if node.field_info.mutable else ChainStep(node.line, node.column, node.field)
        if isinstance(node, IndexNode):
            # An element is as mutable as its array.
            return self.chain_problem(node.object, context)
        if isinstance(node, IdentifierNode):
            info = node.ref
            mutable = info.mutable if isinstance(info, FieldInfo) else info.kind == "mutable"
            return None if mutable else ChainStep(node.line, node.column, info.name)
        return ChainStep(node.line, node.column, None)

    # --------------------------------------------------------- expressions

    def require(self, node, expected, context):
        actual = self.expression(node, expected, context)
        if actual != expected:
            raise error(node, f"Типи не б'ються: чекаю «{word(expected)}», а тут «{word(actual)}».")
        return actual

    def require_integer(self, node, expected, context):
        actual = self.expression(node, expected, context)
        if not is_integer(actual):
            raise error(node, f"Тут треба ціле число, а не «{word(actual)}».")
        return actual

    def expression(self, node, expected, context):
        """Check an expression and store its type; expected guides literal types only."""
        node.type = self.expression_type(node, expected, context)
        return node.type

    def expression_type(self, node, expected, context):
        if context.const_only and not isinstance(
                node, (IntegerNode, BooleanNode, IdentifierNode, UnaryNode, BinaryNode)):
            raise error(node, f"У {context.const_of} тільки числа, «реально»/«гон», операції й інші константи.")
        value = literal_value(node)
        if value is not None:
            result = expected if is_integer(expected) else I64
            low, high = result.range
            if not low <= value <= high:
                raise error(node, f"Число {value} не влазить у «{word(result)}»: "
                                  f"там від {low} до {high}.")
            if isinstance(node, UnaryNode):
                self.mark_literal(node, result)
            return result
        if isinstance(node, BooleanNode):
            return BOOL
        if isinstance(node, ReadNode):
            if is_integer(expected):
                return expected
            if expected is None:
                return I64
            raise error(node, f"«Ану кажи» читає ціле число, а тут чекаю «{word(expected)}».")
        if isinstance(node, IdentifierNode):
            if context.const_only:
                node.ref = context.scope.lookup(node.name)
                if node.ref is None:
                    raise error(node, f"«{node.name}» — не константа: у {context.const_of} можна тільки "
                                      f"константи, оголошені вище.")
                return node.ref.type
            node.ref = self.lookup_value(node.name, node, context)
            return node.ref.type
        if isinstance(node, UnaryNode):
            return self.require_integer(node.operand, expected, context)
        if isinstance(node, BinaryNode):
            return self.binary_type(node, expected, context)
        if isinstance(node, CallNode):
            return self.call_type(node, context)
        if isinstance(node, MemberCallNode):
            return self.member_call_type(node, context)
        if isinstance(node, FieldAccessNode):
            object_type = self.expression(node.object, None, context)
            if is_variant(object_type):
                return self.check_type(node, object_type)
            if isinstance(object_type, ArrayType):
                if node.field != LENGTH:
                    raise error(node, f"У масиву нема поля «{node.field}»: є тільки «{LENGTH}».")
                # Rule 36: a constant, typed like an integer literal; дрібняк without context.
                node.field_info = None
                node.length = object_type.length
                return expected if is_integer(expected) else I32
            structure = self.structure_of(object_type, node.object)
            if node.field not in structure.fields:
                raise error(node, f"В «{structure.name}» нема поля «{node.field}».")
            node.field_info = structure.fields[node.field]
            return node.field_info.type
        if isinstance(node, NewObjectNode):
            if node.structure not in self.structures:
                raise error(node, f"Шо за структура «{node.structure}»? Такої «такі діла» нема.")
            structure = self.structures[node.structure]
            fields = list(structure.fields.values())
            what = f"«склепай {structure.name}»"
            if len(node.arguments) > len(fields):
                raise error(node, f"{what} чекає не більше {count(len(fields))}, а дали {len(node.arguments)}.")
            # Auto constructor: the values fill the first fields; the rest use their defaults.
            given = fields[:len(node.arguments)]
            for missing in fields[len(node.arguments):]:
                if not missing.has_default:
                    raise error(node, f"{what} не дав значення полю «{missing.name}», "
                                      f"а свого «це» в нього нема.")
            self.check_arguments(node, node.arguments, [f.type for f in given], what, context)
            return StructType(structure.name)
        if isinstance(node, IndexNode):
            return self.index_type(node, context)
        if isinstance(node, VariantNode):
            return self.variant_type(node, expected, context)
        if isinstance(node, TryNode):
            return self.try_type(node, context)
        if isinstance(node, ArrayLiteralNode):
            return self.array_literal_type(node, expected, context)
        if isinstance(node, ArrayFillNode):
            if not isinstance(expected, ArrayType):
                raise error(node, "«[всюди …]» не знає, скільки штук: тут не видно, який масив треба. "
                                  "Вкажи тип через «тіпа» або перелічи елементи.")
            self.require(node.value, expected.element, context)
            return expected
        raise error(node, "Такий вираз тут не канає.")

    def index_type(self, node, context):
        # Rule 35: an integer index; one known now must be inside the array.
        array_type = self.expression(node.object, None, context)
        if not isinstance(array_type, ArrayType):
            raise error(node, f"«{word(array_type)}» — не масив, номером у нього не ткнеш.")
        self.require_integer(node.index, None, context)
        value = constant_value(node.index)
        if value is not None and not 0 <= value < array_type.length:
            raise error(node.index, f"Номер {value} за межами масиву: у «{word(array_type)}» можна від 0 "
                                    f"до {array_type.length - 1}.")
        node.index_value = value
        return array_type.element

    def check_type(self, node, object_type):
        # Rule 40: з.шось and з.нема on може, р.вийшло and р.облом on вийде.
        allowed = ("шось", "нема") if isinstance(object_type, OptionType) else ("вийшло", "облом")
        if node.field not in allowed:
            raise error(node, f"У «{word(object_type)}» нема поля «{node.field}»: є тільки "
                              f"«{allowed[0]}» і «{allowed[1]}».")
        node.field_info = None
        node.variant = CHECKS[node.field]
        return BOOL

    def variant_type(self, node, expected, context):
        # Rule 39: шось(x) and нема make може, вийшло(x) and облом(e) make вийде.
        if node.variant in ("some", "none"):
            if isinstance(expected, OptionType):
                if node.value is not None:
                    self.require(node.value, expected.inner, context)
                return expected
            if node.value is None and expected is not None:
                raise error(node, f"«Нема» робить «може …», а тут чекаю «{word(expected)}».")
            if node.value is None:
                raise error(node, "«Нема» не знає, чого нема: тут не видно, який «може» треба. "
                                  "Вкажи тип через «тіпа».")
            return OptionType(self.expression(node.value, None, context))
        word_of = "вийшло" if node.variant == "ok" else "облом"
        if expected is not None and not isinstance(expected, ResultType):
            raise error(node, f"«{word_of.capitalize()}» робить «вийде … або облом …», "
                              f"а тут чекаю «{word(expected)}».")
        if not isinstance(expected, ResultType):
            raise error(node, f"«{word_of.capitalize()}» не знає, який тут «вийде … або облом …»: "
                              f"вкажи тип через «тіпа».")
        self.require(node.value, expected.ok if node.variant == "ok" else expected.error, context)
        return expected

    def try_type(self, node, context):
        # Rule 47: з? is what шось or вийшло holds. Inside a function, нема or облом
        # leaves it, so the function must return that same kind of value; in the
        # main program they stop the program.
        held = self.expression(node.operand, None, context)
        if not isinstance(held, (OptionType, ResultType)):
            raise error(node, f"«?» розпаковує тільки «може» або «вийде», а тут «{word(held)}».")
        function = context.function
        if function is not None:
            result = function.result
            if isinstance(held, OptionType) and not isinstance(result, OptionType):
                raise error(node, f"«?» при «нема» вертає «нема» з функції, тож {function.describe()} "
                                  f"має віддавати «може …», а віддає «{word(result)}».")
            if isinstance(held, ResultType) and not (isinstance(result, ResultType)
                                                     and result.error == held.error):
                raise error(node, f"«?» при «облом» вертає його з функції, тож {function.describe()} "
                                  f"має віддавати «вийде … або облом {held.error.word}», "
                                  f"а віддає «{word(result)}».")
        return held.inner if isinstance(held, OptionType) else held.ok

    def fallback_type(self, node, expected, context):
        """з або x: what з holds, or x when it holds nothing; або on базар stays logical OR."""
        node.fallback = False
        if is_flexible(node.left):
            self.require(node.left, BOOL, context)
            self.require(node.right, BOOL, context)
            return BOOL
        left_type = self.expression(node.left, None, context)
        if left_type == BOOL:
            self.require(node.right, BOOL, context)
            return BOOL
        if not is_variant(left_type):
            raise error(node.left, f"Типи не б'ються: чекаю «базар», а тут «{word(left_type)}».")
        # Rule 41: the fallback has the type that шось or вийшло holds.
        node.fallback = True
        inner = left_type.inner if isinstance(left_type, OptionType) else left_type.ok
        self.require(node.right, inner, context)
        return inner

    def array_literal_type(self, node, expected, context):
        """[a, b, c]: all elements of one type, which an expected array gives to literals."""
        if isinstance(expected, ArrayType):
            element = expected.element
            for item in node.elements:
                self.require(item, element, context)
        else:
            # Like an operator: the first element with its own type sets it.
            first = first_typed(node.elements)
            element = self.expression(first, None, context)
            for item in node.elements:
                if item is not first:
                    self.require(item, element, context)
        return ArrayType(element, len(node.elements))

    def mark_literal(self, node, type_name):
        while isinstance(node, UnaryNode):
            node.type = type_name
            node = node.operand
        node.type = type_name

    def binary_type(self, node, expected, context):
        operator = node.operator
        if operator == "or":
            return self.fallback_type(node, expected, context)
        if operator in LOGIC:
            self.require(node.left, BOOL, context)
            self.require(node.right, BOOL, context)
            return BOOL
        if operator in ARITHMETIC and is_integer(expected):
            self.require(node.left, expected, context)
            self.require(node.right, expected, context)
            return expected
        # No integer context: the first operand with its own type sets it.
        if not is_flexible(node.left):
            operand_type = self.expression(node.left, None, context)
            self.require_operand(node.right, operand_type, node, context)
        elif not is_flexible(node.right):
            operand_type = self.expression(node.right, None, context)
            self.require_operand(node.left, operand_type, node, context)
        elif isinstance(node.left, (ArrayLiteralNode, ArrayFillNode, VariantNode)):
            first = first_typed([node.left, node.right])
            other = node.right if first is node.left else node.left
            operand_type = self.expression(first, None, context)
            self.require_operand(other, operand_type, node, context)
        else:
            operand_type = I64
            self.require(node.left, I64, context)
            self.require(node.right, I64, context)
        if operator in EQUALITY:
            if not is_comparable(operand_type):
                raise error(node, f"Об'єкти «{word(operand_type)}» не порівнюють: "
                                  f"«рівно» тільки для чисел, базару й того, що з них складено.")
            return BOOL
        if not is_integer(operand_type):
            raise error(node, f"Тут треба цілі числа, а не «{word(operand_type)}».")
        return BOOL if operator in ORDERING else operand_type

    def require_operand(self, node, expected, parent, context):
        actual = self.expression(node, expected, context)
        if actual != expected:
            raise error(parent, f"Типи не б'ються: зліва «{word(parent.left.type)}», "
                                f"справа «{word(parent.right.type)}».")

    def call_type(self, node, context):
        target = None
        node.on_self = False
        structure = context.structure
        if structure is not None and node.name in structure.methods:
            # Rule 9: a bare call inside a member function finds the structure's members first.
            target = structure.methods[node.name]
            node.on_self = True
            context.function.depends_on.add(target)
        elif node.name in self.functions:
            target = self.functions[node.name]
        if target is None:
            raise error(node, f"Шо за функція «{node.name}»? Такої «маю дєло» нема.")
        node.target = target
        self.check_arguments(node, node.arguments, [p.type for p in target.parameters],
                             target.describe(), context)
        return target.result

    def member_call_type(self, node, context):
        structure = self.object_structure(node.object, context)
        if node.method not in structure.methods:
            raise error(node, f"В «{structure.name}» нема функції «{node.method}».")
        target = structure.methods[node.method]
        node.target = target
        self.check_arguments(node, node.arguments, [p.type for p in target.parameters],
                             target.describe(), context)
        if isinstance(chain_root(node.object), IdentifierNode) and isinstance(
                chain_root(node.object).ref, FieldInfo):
            # A call on one of the own fields mutates the own object if the callee mutates.
            context.function.depends_on.add(target)
        self.member_calls.append(MemberCallSite(node, target, self.chain_problem(node.object, context)))
        return target.result

    def object_structure(self, node, context):
        return self.structure_of(self.expression(node, None, context), node)

    def structure_of(self, object_type, node):
        if not isinstance(object_type, StructType):
            raise error(node, f"«{word(object_type)}» — не об'єкт, у нього нема полів і функцій.")
        return self.structures[object_type.name]

    def check_arguments(self, node, arguments, types, what, context):
        # Rule 11, 17: the number and the types of the arguments.
        if len(arguments) != len(types):
            raise error(node, f"{what} чекає {count(len(types))}, а дали {len(arguments)}.")
        for number, (argument, expected) in enumerate(zip(arguments, types), start=1):
            actual = self.expression(argument, expected, context)
            if actual != expected:
                raise error(argument, f"Аргумент {number} для {what}: чекаю «{word(expected)}», "
                                      f"а тут «{word(actual)}».")

    def lookup_value(self, name, node, context):
        # Rule 6, 7, 8: scopes, then the fields of the own structure, then constants.
        info = context.scope.lookup(name)
        if info is None and context.structure is not None:
            info = context.structure.fields.get(name)
        if info is None and context.function is not None:
            info = self.constants.get(name)
        if info is None:
            raise error(node, f"Шо за «{name}»? Такого тут ніхто не оголошував.")
        return info

    # ------------------------------------------------------------ mutation

    def resolve_mutation(self):
        # Rule 23: repeat until no member function changes its flag.
        methods = [m for s in self.structures.values() for m in s.methods.values()]
        for method in methods:
            method.mutating = method.assigns_field
        changed = True
        while changed:
            changed = False
            for method in methods:
                if not method.mutating and any(d.mutating for d in method.depends_on):
                    method.mutating = changed = True
        # Rule 24: a mutating member function is called only on a mutable chain.
        for site in sorted(self.member_calls, key=lambda s: (s.node.line, s.node.column)):
            if site.target.mutating and site.problem:
                if site.problem.name is None:
                    raise error(site.node, f"{site.target.describe()} міняє поля, а тут тимчасове значення: "
                                           f"зміни пропадуть. Збережи об'єкт у «мутна тєма».")
                raise error(site.node, f"{site.target.describe()} міняє поля, а «{site.problem.name}» "
                                       f"— не «мутна тєма». Таке кличуть тільки на мутному об'єкті.")


def analyze(program):
    """Check the program and annotate its AST; return the symbol table."""
    return Analyzer().analyze(program)
