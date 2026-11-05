"""Bazar optimizer: three transformations of the checked tree behind --optimize.

    optimize(program, info)

Runs after semantic.analyze() and before code generation, and changes the tree
and the symbol table in place. The transformations repeat until none of them
finds anything more to do, because each can give work to the others:

* unused functions: a function that cannot be reached from the main program is
  removed with its body. Reachability also removes functions that only call
  each other;
* unused variables: a declaration nobody reads is removed with its assignments.
  Names are compared by their VarInfo from the semantic pass, not by spelling,
  so scopes and shadowing are respected without any extra work;
* inlining: a function called exactly once is replaced at its call site by its
  body, as described at can_inline() and call_can_move().

The output of a program is the same with and without the flag, including its
run-time errors: nodes keep their line and column, so a moved expression
reports the same position.
"""

from ast_nodes import (
    ArrayFillNode, ArrayLiteralNode, AssignmentNode, ASTNode, BinaryNode, BindingPatternNode, BlockNode,
    BooleanNode, CallNode, CallStatementNode, DeclarationNode, ExitNode, FieldAccessNode, FieldAssignmentNode,
    ForEachNode, ForNode, FunctionNode, IdentifierNode, IfNode, IndexNode, IntegerNode, MatchNode,
    MemberCallNode, NewObjectNode, PrintNode, ReturnNode, StructureNode, TryNode, UnaryNode, VariantNode,
    WhileNode, walk,
)
from semantic import VarInfo, constant_value

ARITHMETIC = ("add", "sub", "mul", "div")


# ---------------------------------------------------------------- tree walks

def contains(node, target):
    return any(item is target for item in walk(node))


def main_statements(program):
    return [s for s in program.statements if not isinstance(s, (FunctionNode, StructureNode))]


def all_functions(info):
    yield from info.functions.values()
    for structure in info.structures.values():
        yield from structure.methods.values()


def statement_lists(program, info):
    """Every list of statements in the program, nested blocks included."""
    roots = [program.statements] + [f.node.body.statements for f in all_functions(info)]
    for statements in roots:
        yield statements
        for statement in statements:
            if not isinstance(statement, (FunctionNode, StructureNode)):
                for item in walk(statement):
                    if isinstance(item, BlockNode):
                        yield item.statements


def code_of(program, info):
    """Every statement that can run: the main program and all function bodies."""
    yield from main_statements(program)
    for function in all_functions(info):
        yield function.node.body


def called_from(node):
    """The functions a piece of code calls directly."""
    for item in walk(node):
        if isinstance(item, (CallNode, MemberCallNode)):
            yield item.target


# ---------------------------------------------------------- unused functions

def remove_unused_functions(program, info):
    """Remove every function the main program cannot reach, with its whole body."""
    reached = set()
    pending = [target for statement in main_statements(program) for target in called_from(statement)]
    while pending:
        function = pending.pop()
        if function not in reached:
            reached.add(function)
            pending.extend(called_from(function.node.body))
    changed = False
    for name, function in list(info.functions.items()):
        if function not in reached:
            del info.functions[name]
            program.statements.remove(function.node)
            changed = True
    for structure in info.structures.values():
        for name, method in list(structure.methods.items()):
            if method not in reached:
                del structure.methods[name]
                structure.node.methods.remove(method.node)
                changed = True
    return changed


# ---------------------------------------------------------- unused variables

def can_drop(node):
    """Whether removing an expression cannot change what the program does.

    A call or ану кажи is never dropped. Neither is arithmetic that could stop
    the program with an overflow or a division by zero: that error is output
    too. Arithmetic on values known now is checked and can be dropped."""
    if isinstance(node, (IntegerNode, BooleanNode, IdentifierNode)):
        return True
    if isinstance(node, FieldAccessNode):
        return can_drop(node.object)
    if isinstance(node, IndexNode):
        # An index the semantic pass knows is inside the array; any other may stop the program.
        return can_drop(node.object) and node.index_value is not None
    if isinstance(node, NewObjectNode):
        return all(can_drop(argument) for argument in node.arguments)
    if isinstance(node, ArrayLiteralNode):
        return all(can_drop(item) for item in node.elements)
    if isinstance(node, ArrayFillNode):
        return can_drop(node.value)
    if isinstance(node, VariantNode):
        return node.value is None or can_drop(node.value)
    if isinstance(node, BinaryNode) and node.operator not in ARITHMETIC:
        return can_drop(node.left) and can_drop(node.right)
    if isinstance(node, (UnaryNode, BinaryNode)):
        return constant_value(node) is not None
    return False


def place_root(node):
    while isinstance(node, (FieldAccessNode, IndexNode)):
        node = node.object
    return node


def place_chain(node):
    """The steps of an assignment target down to its name, without its index expressions."""
    while isinstance(node, (FieldAccessNode, IndexNode)):
        yield node
        node = node.object
    yield node


def place_indexes(node):
    return [step.index for step in place_chain(node) if isinstance(step, IndexNode)]


def removable_variables(program, info):
    """The declared variables nobody reads and whose every value can be dropped."""
    declared, kept, read_places = set(), set(), set()
    for code in code_of(program, info):
        for item in walk(code):
            if isinstance(item, DeclarationNode):
                declared.add(item.info)
                if not can_drop(item.initializer):
                    kept.add(item.info)
            elif isinstance(item, AssignmentNode):
                if not can_drop(item.value):
                    kept.add(item.ref)
            elif isinstance(item, FieldAssignmentNode):
                # An assignment through п.х or а[і] writes п or а; it does not read it.
                # The index і is read, and it runs whenever the assignment does.
                read_places.update(id(step) for step in place_chain(item.target))
                if not (can_drop(item.value) and all(can_drop(index) for index in place_indexes(item.target))):
                    kept.add(place_root(item.target).ref)
    for code in code_of(program, info):
        for item in walk(code):
            if isinstance(item, IdentifierNode) and id(item) not in read_places:
                kept.add(item.ref)
    return declared - kept


def remove_unused_variables(program, info):
    """One pass; the caller repeats it, since a removal may leave another variable unread."""
    removable = removable_variables(program, info)
    if not removable:
        return False

    def is_unused(statement):
        if isinstance(statement, DeclarationNode):
            return statement.info in removable
        if isinstance(statement, AssignmentNode):
            return statement.ref in removable
        if isinstance(statement, FieldAssignmentNode):
            return place_root(statement.target).ref in removable
        return False

    for statements in statement_lists(program, info):
        statements[:] = [s for s in statements if not is_unused(s)]
    return True


# ------------------------------------------------------------------ inlining

def can_inline(function):
    """The shape that is inlined: a top-level function that leaves only by its last line.

    A member function uses the fields of its object, and a тримай anywhere else
    would need a jump out of the middle of the caller's code. So would a ?, which
    returns нема or облом from the function: moved into the caller, it would
    leave the caller instead."""
    if function.owner is not None:
        return False
    if any(isinstance(item, TryNode) for item in walk(function.node.body)):
        return False
    statements = function.node.body.statements
    if not isinstance(statements[-1], ReturnNode):
        return False
    returns = [item for item in walk(function.node.body) if isinstance(item, ReturnNode)]
    return len(returns) == 1


def is_recursive(function):
    seen, pending = set(), list(called_from(function.node.body))
    while pending:
        current = pending.pop()
        if current is function:
            return True
        if current not in seen:
            seen.add(current)
            pending.extend(called_from(current.node.body))
    return False


def is_plain(node):
    """A value that neither runs code nor can fail, so it may be read after a moved body.

    The moved body cannot change it: a function sees only its own parameters and
    locals, and objects are passed by value."""
    if isinstance(node, (IntegerNode, BooleanNode, IdentifierNode)):
        return True
    if isinstance(node, UnaryNode):
        return isinstance(node.operand, IntegerNode)
    return isinstance(node, FieldAccessNode) and is_plain(node.object)


def evaluated_parts(node):
    """The operands of an expression in the order the generated code evaluates them."""
    if isinstance(node, BinaryNode):
        return [node.left, node.right]
    if isinstance(node, UnaryNode):
        return [node.operand]
    if isinstance(node, (CallNode, NewObjectNode)):
        return node.arguments
    if isinstance(node, MemberCallNode):
        return [node.object] + node.arguments
    if isinstance(node, FieldAccessNode):
        return [node.object]
    if isinstance(node, IndexNode):
        return [node.object, node.index]
    if isinstance(node, ArrayLiteralNode):
        return node.elements
    if isinstance(node, ArrayFillNode):
        return [node.value]
    if isinstance(node, VariantNode):
        return [] if node.value is None else [node.value]
    if isinstance(node, TryNode):
        return [node.operand]
    return []


def call_can_move(expression, call):
    """Whether the call may run before the rest of its expression without anyone noticing.

    The body moves in front of the statement, so everything evaluated before
    the call has to be plain. The right side of і ше and або may never run at
    all, so a call there stays where it is."""
    if expression is call:
        return True
    parts = evaluated_parts(expression)
    if isinstance(expression, BinaryNode) and expression.operator in ("and", "or"):
        parts = parts[:1]
    for part in parts:
        if contains(part, call):
            return call_can_move(part, call)
        if not is_plain(part):
            return False
    return False


def statement_expressions(statement):
    """The expressions a statement evaluates once, in order, before anything else it does.

    The condition of a while loop is not here: it runs on every pass, so a body
    moved in front of the loop would run only once."""
    if isinstance(statement, DeclarationNode):
        return [statement.initializer]
    if isinstance(statement, (AssignmentNode, FieldAssignmentNode, PrintNode, ExitNode, ReturnNode)):
        return [statement.value]
    if isinstance(statement, CallStatementNode):
        return [statement.call]
    if isinstance(statement, IfNode):
        return [statement.condition]
    if isinstance(statement, ForNode):
        return [statement.start, statement.end]
    if isinstance(statement, ForEachNode):
        return [statement.array]
    if isinstance(statement, MatchNode):
        return [statement.subject]
    return []


def statement_allows_move(statement, call):
    for expression in statement_expressions(statement):
        if contains(expression, call):
            return call_can_move(expression, call)
        if not is_plain(expression):
            return False
    return False


def replace_child(node, old, new):
    """Replace one expression below node; a node has exactly one parent."""
    for name, value in vars(node).items():
        if value is old:
            setattr(node, name, new)
            return True
        if isinstance(value, ASTNode):
            if replace_child(value, old, new):
                return True
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if item is old:
                    value[index] = new
                    return True
                if isinstance(item, ASTNode) and replace_child(item, old, new):
                    return True
    return False


class Inliner:
    def __init__(self, program, info):
        self.program = program
        self.info = info
        self.count = 0

    def run(self):
        """Inline one call; True if the tree changed."""
        calls = {}
        for code in code_of(self.program, self.info):
            for item in walk(code):
                if isinstance(item, CallNode):
                    calls.setdefault(item.target, []).append(item)
        for function, sites in calls.items():
            if len(sites) == 1 and can_inline(function) and not is_recursive(function):
                if self.inline(function, sites[0]):
                    return True
        return False

    def inline(self, function, call):
        for statements in statement_lists(self.program, self.info):
            for index, statement in enumerate(statements):
                if isinstance(statement, (FunctionNode, StructureNode)):
                    continue
                if statement_allows_move(statement, call):
                    self.move_body(function, call, statements, index)
                    return True
        return False

    def renamed(self, name, function):
        # A "." cannot occur in a source name, so this can collide with nothing.
        return f"{name}.{function.name}.{self.count}"

    def move_body(self, function, call, statements, index):
        self.count += 1
        moved = []
        # Each parameter becomes a local declaration initialised with the argument.
        # The new declarations reuse the type nodes of the function header: the
        # function is removed once nobody calls it, so they have one owner again.
        for parameter, syntax, argument in zip(function.parameters, function.node.parameters, call.arguments):
            parameter.kind = "immutable"
            declaration = DeclarationNode(call.line, call.column, parameter.name, syntax.declared_type,
                                          False, argument)
            declaration.info = parameter
            moved.append(declaration)
        body = function.node.body.statements
        self.rename_locals(function, body, moved)
        moved.extend(body[:-1])
        # The exit of the body becomes the value that stands where the call stood.
        exit_node = body[-1]
        result = VarInfo(self.renamed("результат", function), function.result, "immutable")
        declaration = DeclarationNode(exit_node.line, exit_node.column, result.name, function.node.result_type,
                                      False, exit_node.value)
        declaration.info = result
        moved.append(declaration)
        statement = statements[index]
        if isinstance(statement, CallStatementNode) and statement.call is call:
            statements[index:index + 1] = moved
        else:
            value = IdentifierNode(call.line, call.column, result.name)
            value.ref = result
            value.type = call.type
            replace_child(statement, call, value)
            statements[index:index] = moved
        # Nobody calls the function now: it is removed as unused on the next round.

    def rename_locals(self, function, body, parameters):
        """Give the parameters and locals of the moved body names no caller can have."""
        owned = {declaration.info for declaration in parameters}
        for statement in body:
            for item in walk(statement):
                if isinstance(item, (DeclarationNode, ForNode, ForEachNode, BindingPatternNode)):
                    owned.add(item.info)
        for info in owned:
            info.name = self.renamed(info.name, function)
        for declaration in parameters:
            declaration.name = declaration.info.name
        for statement in body:
            for item in walk(statement):
                if isinstance(item, (DeclarationNode, ForNode, ForEachNode, BindingPatternNode)):
                    item.name = item.info.name
                elif isinstance(item, (IdentifierNode, AssignmentNode)) and item.ref in owned:
                    item.name = item.ref.name


def optimize(program, info):
    """Run the three transformations until a whole round changes nothing."""
    inliner = Inliner(program, info)
    changed = True
    while changed:
        changed = remove_unused_functions(program, info)
        changed = remove_unused_variables(program, info) or changed
        changed = inliner.run() or changed
