"""Bazar code generation: LLVM IR through the llvmlite.ir builder.

    generate(program, info) -> str

Runs after semantic.analyze(), whose annotations it reads: every expression
has .type, names have .ref, calls have .target, field accesses .field_info.
The only IR text the compiler writes is str(module), printed by llvmlite.

Layout of the module:
* an identified struct type "bz.T" per structure, fields in field order;
* "bz.NAME" per function and "bz.T.NAME" per member function, whose first
  parameter is a pointer to the object; the prefix keeps a function named
  main or printf apart from the C runtime;
* "main", the top-level statements;
* printf, scanf, write and exit declared without bodies; clang links them
  against the C library, and llvm.memcpy once an object is copied;
* format strings and string literals as private global constants.

Every variable lives in an alloca of its function's entry block. A scalar
(integer or базар) is an SSA value. An object (an aggregate) is never loaded
or stored as a whole, because LLVM compiles large aggregate values in
superlinear time: it stays in memory, and its value is copied with
llvm.memcpy. pointer() gives the memory of an object, emit_into() writes an
object's value straight into memory that the expression cannot see, and
snapshot() copies it into a fresh temporary. An object parameter is a pointer
that the callee only reads; an object result is written through a hidden first
parameter that points to memory of the caller.

Arithmetic uses the *.with.overflow intrinsics; an overflow, a division by
zero, or MIN ділити на мінус 1 writes one line to stderr and exits with 1.
"""

from llvmlite import ir
import llvmlite.binding as llvm

from ast_nodes import (
    AssignmentNode, BinaryNode, BooleanNode, BreakNode, CallNode, CallStatementNode, DeclarationNode,
    ExitNode, FieldAccessNode, FieldAssignmentNode, ForNode, IdentifierNode, IfNode, IntegerNode,
    MemberCallNode, NewObjectNode, PrintNode, ReadNode, ReturnNode, StringNode, UnaryNode, WhileNode, walk,
)
from bazar_types import BoolType, IntType, StructType, is_aggregate, is_scalar
from semantic import FieldInfo

I1, I8, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(32), ir.IntType(64)
I8_PTR = I8.as_pointer()
INT_LLTYPES = {32: I32, 64: I64}         # IntType.bits -> LLVM type
INT_FORMATS = {32: "%d", 64: "%lld"}     # IntType.bits -> printf and scanf format
COMPARISONS = {"eq": "==", "ne": "!=", "gt": ">", "lt": "<"}
OVERFLOW_WORDS = {"add": "плюс", "sub": "мінус", "mul": "на"}
EXIT_MESSAGE = "Всьо, розходимось: %lld\n"


class CodeGenerator:
    def __init__(self, info):
        self.info = info
        self.module = ir.Module(name="bazar")
        self.module.triple = llvm.get_default_triple()
        self.strings = {}                    # text -> global constant
        self.struct_types = {}
        self.functions = {}                  # FunctionInfo -> ir.Function
        self.memcpy_function = None          # declared on the first copy of an object
        self.declare_runtime()
        self.declare_structures()
        self.declare_functions()

    # ------------------------------------------------------------- module

    def declare_runtime(self):
        c_variadic = ir.FunctionType(I32, [I8_PTR], var_arg=True)     # int f(const char *fmt, ...)
        self.printf = ir.Function(self.module, c_variadic, name="printf")
        self.scanf = ir.Function(self.module, c_variadic, name="scanf")
        self.write = ir.Function(self.module, ir.FunctionType(I64, [I32, I8_PTR, I64]), name="write")
        self.exit = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I32]), name="exit")

    def declare_structures(self):
        # All names first, then bodies: a field may have a structure declared below.
        for name in self.info.structures:
            self.struct_types[name] = self.module.context.get_identified_type(f"bz.{name}")
        for name, structure in self.info.structures.items():
            self.struct_types[name].set_body(*(self.lltype(f.type) for f in structure.fields.values()))

    def declare_functions(self):
        # Every function is declared before any body, so a call to one defined later resolves.
        for function in self.info.functions.values():
            self.declare_function(function, f"bz.{function.name}", [])
        for structure in self.info.structures.values():
            self_pointer = self.struct_types[structure.name].as_pointer()
            for method in structure.methods.values():
                self.declare_function(method, f"bz.{structure.name}.{method.name}", [self_pointer])

    def declare_function(self, function, name, leading):
        # An object parameter is a pointer; an object result is written through
        # a pointer that comes before every other parameter.
        parameters = leading + [self.argument_lltype(p.type) for p in function.parameters]
        if is_aggregate(function.result):
            parameters.insert(0, self.lltype(function.result).as_pointer())
            result = ir.VoidType()
        else:
            result = self.lltype(function.result)
        self.functions[function] = ir.Function(self.module, ir.FunctionType(result, parameters), name=name)

    def argument_lltype(self, t):
        return self.lltype(t).as_pointer() if is_aggregate(t) else self.lltype(t)

    def lltype(self, t):
        """The LLVM type of a bazar_types.Type."""
        if isinstance(t, IntType):
            return INT_LLTYPES[t.bits]
        if isinstance(t, BoolType):
            return I1
        if isinstance(t, StructType):
            return self.struct_types[t.name]
        raise AssertionError(f"no LLVM type for {t}")

    def string(self, text):
        """A pointer to a private global constant holding text and a NUL byte."""
        if text not in self.strings:
            data = bytearray(text.encode("utf-8") + b"\0")
            array = ir.ArrayType(I8, len(data))
            constant = ir.GlobalVariable(self.module, array, name=f"str.{len(self.strings)}")
            constant.global_constant = True
            constant.linkage = "private"
            constant.initializer = ir.Constant(array, data)
            self.strings[text] = constant
        return self.strings[text].gep([ir.Constant(I32, 0), ir.Constant(I32, 0)])

    def memcpy(self):
        if self.memcpy_function is None:
            self.memcpy_function = self.module.declare_intrinsic("llvm.memcpy", [I8_PTR, I8_PTR, I64])
        return self.memcpy_function

    def generate(self, program):
        for function in self.info.functions.values():
            self.generate_body(function, self.functions[function], None)
        for structure in self.info.structures.values():
            for method in structure.methods.values():
                self.generate_body(method, self.functions[method], structure)
        self.generate_main(program)
        return str(self.module)

    # ------------------------------------------------------------- bodies

    def begin_function(self, llvm_function):
        self.function = llvm_function
        self.entry = llvm_function.append_basic_block("entry")    # allocas only
        body = llvm_function.append_basic_block("body")
        self.builder = ir.IRBuilder(body)
        self.slots = {}                      # VarInfo -> alloca
        self.loop_ends = []                  # exit block of each enclosing loop, innermost last
        self.self_pointer = None
        self.result_pointer = None           # where тримай writes an object result
        self.structure = None

    def finish_function(self):
        ir.IRBuilder(self.entry).branch(self.function.blocks[1])

    def alloca(self, llvm_type, name=""):
        return ir.IRBuilder(self.entry).alloca(llvm_type, name=name)

    def generate_body(self, function, llvm_function, structure):
        self.begin_function(llvm_function)
        arguments = list(llvm_function.args)
        if is_aggregate(function.result):
            self.result_pointer = arguments.pop(0)
            self.result_pointer.name = "result"
        if structure is not None:
            self.self_pointer = arguments.pop(0)
            self.self_pointer.name = "self"
            self.structure = structure
        for parameter, argument in zip(function.parameters, arguments):
            argument.name = parameter.name
            if is_aggregate(parameter.type):
                self.slots[parameter] = argument          # read only: a parameter is never assigned
                continue
            slot = self.alloca(argument.type, parameter.name)
            self.builder.store(argument, slot)
            self.slots[parameter] = slot
        self.statements(function.node.body.statements)
        if not self.builder.block.is_terminated:
            self.builder.unreachable()       # every path returned (semantic rule 13)
        self.finish_function()

    def generate_main(self, program):
        main = ir.Function(self.module, ir.FunctionType(I32, []), name="main")
        self.begin_function(main)
        self.statements(program.statements)
        if not self.builder.block.is_terminated:
            self.builder.ret(ir.Constant(I32, 0))
        self.finish_function()

    def new_block(self, name):
        return self.function.append_basic_block(name)

    # --------------------------------------------------------- statements

    def statements(self, statements):
        for node in statements:
            if self.builder.block.is_terminated:
                # Statements after всьо розходимось run in no path, but still need a block.
                self.builder.position_at_end(self.new_block("dead"))
            self.statement(node)

    def statement(self, node):
        if isinstance(node, DeclarationNode):
            slot = self.alloca(self.lltype(node.info.type), node.name)
            if is_aggregate(node.info.type):
                self.emit_into(slot, node.initializer)    # the initializer cannot see the new name
            else:
                self.builder.store(self.value(node.initializer), slot)
            self.slots[node.info] = slot
        elif isinstance(node, AssignmentNode):
            self.assign(lambda: self.name_address(node.ref), False, node.value)
        elif isinstance(node, FieldAssignmentNode):
            self.assign(lambda: self.pointer(node.target), has_call(node.target), node.value)
        elif isinstance(node, PrintNode):
            self.print_statement(node.value)
        elif isinstance(node, ExitNode):
            value = self.value(node.value)
            if value.type == I32:
                value = self.builder.sext(value, I64)
            self.builder.call(self.printf, [self.string(EXIT_MESSAGE), value])
            self.builder.ret(ir.Constant(I32, 0))
        elif isinstance(node, ReturnNode):
            if self.result_pointer is None:
                self.builder.ret(self.value(node.value))
            else:
                self.emit_into(self.result_pointer, node.value)    # memory of the caller
                self.builder.ret_void()
        elif isinstance(node, CallStatementNode):
            self.operand(node.call)
        elif isinstance(node, IfNode):
            self.if_statement(node)
        elif isinstance(node, WhileNode):
            self.while_statement(node)
        elif isinstance(node, ForNode):
            self.for_statement(node)
        elif isinstance(node, BreakNode):
            self.builder.branch(self.loop_ends[-1])
        # Constant, function, and structure declarations produce no statements.

    def assign(self, target, target_has_call, value_node):
        """Store value_node at the address that target() computes after the value.

        An object is never built straight into its target: склепай Т(п.у, п.х)
        assigned to п reads п while it is built. A place is copied directly
        when nothing runs between reading it and the copy: two places of one
        type are either the same memory or do not overlap, which memcpy allows."""
        if not is_aggregate(value_node.type):
            value = self.value(value_node)
            self.builder.store(value, target())
            return
        if addressable(value_node) and not target_has_call:
            source = self.pointer(value_node)
        else:
            source = self.snapshot(value_node)
        self.copy(target(), source, value_node.type)

    def if_statement(self, node):
        condition = self.value(node.condition)
        then_block = self.new_block("then")
        else_block = self.new_block("else") if node.else_body else None
        end_block = self.new_block("endif")
        self.builder.cbranch(condition, then_block, else_block or end_block)
        for block, body in ((then_block, node.then_body), (else_block, node.else_body)):
            if block is None:
                continue
            self.builder.position_at_end(block)
            self.statements(body.statements)
            if not self.builder.block.is_terminated:
                self.builder.branch(end_block)
        self.builder.position_at_end(end_block)

    def loop_body(self, body, end_block, next_block):
        """Generate a loop body; falling off its end continues at next_block."""
        self.loop_ends.append(end_block)
        self.statements(body.statements)
        self.loop_ends.pop()
        if not self.builder.block.is_terminated:
            self.builder.branch(next_block)

    def while_statement(self, node):
        cond_block = self.new_block("while.cond")
        body_block = self.new_block("while.body")
        end_block = self.new_block("while.end")
        self.builder.branch(cond_block)
        self.builder.position_at_end(cond_block)
        self.builder.cbranch(self.value(node.condition), body_block, end_block)
        self.builder.position_at_end(body_block)
        self.loop_body(node.body, end_block, cond_block)      # the back edge
        self.builder.position_at_end(end_block)

    def for_statement(self, node):
        # The counter is compared with the end before it grows, never after, so
        # a range ending at the largest value of the type stops without overflow.
        start = self.value(node.start)
        end = self.value(node.end)
        slot = self.alloca(start.type, node.name)
        self.slots[node.info] = slot
        self.builder.store(start, slot)
        body_block = self.new_block("for.body")
        step_block = self.new_block("for.step")
        next_block = self.new_block("for.next")
        end_block = self.new_block("for.end")
        self.builder.cbranch(self.builder.icmp_signed("<=", start, end), body_block, end_block)
        self.builder.position_at_end(body_block)
        self.loop_body(node.body, end_block, step_block)
        self.builder.position_at_end(step_block)
        counter = self.builder.load(slot, name=node.name)
        self.builder.cbranch(self.builder.icmp_signed("==", counter, end), end_block, next_block)
        self.builder.position_at_end(next_block)
        self.builder.store(self.builder.add(counter, ir.Constant(counter.type, 1), flags=["nsw"]), slot)
        self.builder.branch(body_block)                       # the back edge
        self.builder.position_at_end(end_block)

    # -------------------------------------------------------------- print

    def print_statement(self, node):
        if isinstance(node, StringNode):
            self.builder.call(self.printf, [self.string("%s\n"), self.string(node.value)])
            return
        self.print_value(self.operand(node), node.type, "", "\n")

    def print_value(self, value, t, prefix, suffix):
        """printf prefix, the value, and suffix; objects walk their field table.

        value is an SSA value for a scalar and a pointer for an object."""
        if isinstance(t, IntType):
            self.builder.call(self.printf, [self.string(prefix + INT_FORMATS[t.bits] + suffix), value])
        elif isinstance(t, BoolType):
            text = self.builder.select(value, self.string("реально"), self.string("гон"))
            self.builder.call(self.printf, [self.string(prefix + "%s" + suffix), text])
        elif isinstance(t, StructType):
            structure = self.info.structures[t.name]
            opening = f"{prefix}{t.name} {{"
            fields = list(structure.fields.values())
            if not fields:
                self.builder.call(self.printf, [self.string(opening + "}" + suffix)])
                return
            for number, field in enumerate(fields):
                pointer = self.element(value, field.index)
                field_value = pointer if is_aggregate(field.type) else self.builder.load(pointer)
                separator = opening + " " if number == 0 else ", "
                closing = " }" + suffix if number == len(fields) - 1 else ""
                self.print_value(field_value, field.type, f"{separator}{field.name}: ", closing)
        else:
            raise AssertionError(f"no printing for {t}")

    # -------------------------------------------------------- expressions

    def value(self, node):
        if isinstance(node, IntegerNode):
            return ir.Constant(self.lltype(node.type), int(node.value))
        if isinstance(node, BooleanNode):
            return ir.Constant(I1, int(node.value))
        if isinstance(node, IdentifierNode):
            if not isinstance(node.ref, FieldInfo) and node.ref.kind == "const":
                return ir.Constant(self.lltype(node.ref.type), int(node.ref.value))
            return self.builder.load(self.name_address(node.ref), name=node.name)
        if isinstance(node, ReadNode):
            slot = self.alloca(self.lltype(node.type))
            self.builder.store(ir.Constant(self.lltype(node.type), 0), slot)   # 0 when input ends
            self.builder.call(self.scanf, [self.string(INT_FORMATS[node.type.bits]), slot])
            return self.builder.load(slot)
        if isinstance(node, UnaryNode):
            if isinstance(node.operand, IntegerNode):
                return ir.Constant(self.lltype(node.type), -int(node.operand.value))
            operand = self.value(node.operand)
            return self.checked(self.builder.ssub_with_overflow, ir.Constant(operand.type, 0),
                                operand, node, "мінус")
        if isinstance(node, BinaryNode):
            return self.binary(node)
        if isinstance(node, FieldAccessNode):
            return self.builder.load(self.pointer(node), name=node.field)
        if isinstance(node, (CallNode, MemberCallNode)):
            return self.call(node, None)
        raise AssertionError(f"no scalar code for {type(node).__name__}")

    def operand(self, node):
        """An SSA value for a scalar expression, a pointer for an object."""
        return self.pointer(node) if is_aggregate(node.type) else self.value(node)

    # ------------------------------------------------------------ objects

    def pointer(self, node):
        """The memory of a name, a field, or an object expression.

        Names and fields are borrowed: the pointer is read before anything else
        runs. Any other object is built in a fresh temporary."""
        if isinstance(node, IdentifierNode):
            return self.name_address(node.ref)
        if isinstance(node, FieldAccessNode):
            # A field is reached with a gep by its index from the symbol table.
            return self.element(self.pointer(node.object), node.field_info.index, node.field)
        return self.snapshot(node)

    def snapshot(self, node):
        """A fresh temporary holding the value of an object expression."""
        temporary = self.alloca(self.lltype(node.type))
        self.emit_into(temporary, node)
        return temporary

    def emit_into(self, destination, node):
        """Write the value of an object expression to memory that node cannot see."""
        if isinstance(node, NewObjectNode):
            self.build_object(destination, node)
        elif isinstance(node, (CallNode, MemberCallNode)):
            self.call(node, destination)
        else:
            self.copy(destination, self.pointer(node), node.type)

    def build_object(self, destination, node):
        """склепай: the given values in field order, then the defaults of the fields left out."""
        for field in self.info.structures[node.structure].fields.values():
            pointer = self.element(destination, field.index)
            if field.index >= len(node.arguments):
                self.store_default(pointer, field)
            elif is_aggregate(field.type):
                self.emit_into(pointer, node.arguments[field.index])
            else:
                self.builder.store(self.value(node.arguments[field.index]), pointer)

    def store_default(self, pointer, field):
        if is_scalar(field.type):
            self.builder.store(ir.Constant(self.lltype(field.type), int(field.default)), pointer)
            return
        for inner in self.info.structures[field.type.name].fields.values():
            self.store_default(self.element(pointer, inner.index), inner)

    def element(self, pointer, index, name=""):
        return self.builder.gep(pointer, [ir.Constant(I32, 0), ir.Constant(I32, index)], name=name)

    def copy(self, destination, source, t):
        size = ir.Constant(self.lltype(t).as_pointer(), None).gep([ir.Constant(I32, 1)]).ptrtoint(I64)
        self.builder.call(self.memcpy(), [self.builder.bitcast(destination, I8_PTR),
                                          self.builder.bitcast(source, I8_PTR), size, ir.Constant(I1, 0)])

    # -------------------------------------------------------------- calls

    def call(self, node, destination):
        """Call a function; an object result is written to destination."""
        arguments = [] if destination is None else [destination]
        if isinstance(node, MemberCallNode):
            # On a temporary object, only a non-mutating call reaches here (semantic rule 24).
            arguments.append(self.pointer(node.object))
        elif node.on_self:
            arguments.append(self.self_pointer)
        arguments += self.call_arguments(node)
        return self.builder.call(self.functions[node.target], arguments)

    def call_arguments(self, node):
        """Argument values in order; an object argument is a pointer the callee only reads.

        A name or field is passed as it is only when nothing can change it during
        the call: no later argument calls anything, and the callee is not a member
        function, which may change its own object, as in п.посунь(п)."""
        values = []
        for index, (parameter, argument) in enumerate(zip(node.target.parameters, node.arguments)):
            if not is_aggregate(parameter.type):
                values.append(self.value(argument))
            elif (addressable(argument) and node.target.owner is None
                  and not any(has_call(later) for later in node.arguments[index + 1:])):
                values.append(self.pointer(argument))
            else:
                values.append(self.snapshot(argument))
        return values

    def binary(self, node):
        operator = node.operator
        if operator in ("and", "or"):
            return self.short_circuit(node)
        left = self.value(node.left)
        right = self.value(node.right)
        if operator in COMPARISONS:
            return self.builder.icmp_signed(COMPARISONS[operator], left, right)
        if operator == "add":
            return self.checked(self.builder.sadd_with_overflow, left, right, node, "плюс")
        if operator == "sub":
            return self.checked(self.builder.ssub_with_overflow, left, right, node, "мінус")
        if operator == "mul":
            return self.checked(self.builder.smul_with_overflow, left, right, node, "на")
        return self.division(left, right, node)

    def short_circuit(self, node):
        left = self.value(node.left)
        left_block = self.builder.block
        right_block = self.new_block(node.operator + ".right")
        end_block = self.new_block(node.operator + ".end")
        if node.operator == "and":
            self.builder.cbranch(left, right_block, end_block)
        else:
            self.builder.cbranch(left, end_block, right_block)
        self.builder.position_at_end(right_block)
        right = self.value(node.right)
        right_end = self.builder.block
        self.builder.branch(end_block)
        self.builder.position_at_end(end_block)
        result = self.builder.phi(I1)
        result.add_incoming(ir.Constant(I1, int(node.operator == "or")), left_block)
        result.add_incoming(right, right_end)
        return result

    def checked(self, intrinsic, left, right, node, operator_word):
        pair = intrinsic(left, right)
        self.fail_if(self.builder.extract_value(pair, 1), node,
                     f"переповнення в «{operator_word}», результат не влазить у тип")
        return self.builder.extract_value(pair, 0)

    def division(self, left, right, node):
        zero = ir.Constant(right.type, 0)
        self.fail_if(self.builder.icmp_signed("==", right, zero), node, "ділити на нуль не можна")
        minimum = ir.Constant(left.type, -(1 << (left.type.width - 1)))
        overflow = self.builder.and_(self.builder.icmp_signed("==", left, minimum),
                                     self.builder.icmp_signed("==", right, ir.Constant(right.type, -1)))
        self.fail_if(overflow, node, "переповнення в «ділити на», результат не влазить у тип")
        return self.builder.sdiv(left, right)          # truncates toward zero

    def fail_if(self, condition, node, message):
        """Branch to a block that reports a run-time error at node and exits with 1."""
        fail_block = self.new_block("fail")
        ok_block = self.new_block("ok")
        self.builder.cbranch(condition, fail_block, ok_block)
        self.builder.position_at_end(fail_block)
        text = f"помилка виконання: line {node.line}:{node.column}: {message}\n"
        self.builder.call(self.write, [ir.Constant(I32, 2), self.string(text),
                                       ir.Constant(I64, len(text.encode("utf-8")))])
        self.builder.call(self.exit, [ir.Constant(I32, 1)])
        self.builder.unreachable()
        self.builder.position_at_end(ok_block)

    # ---------------------------------------------------------- addresses

    def name_address(self, info):
        if isinstance(info, FieldInfo):          # a field of the own object, inside a member function
            return self.element(self.self_pointer, info.index, info.name)
        return self.slots[info]


def addressable(node):
    """A chain of names and fields that lives in memory, not a temporary."""
    if isinstance(node, IdentifierNode):
        return isinstance(node.ref, FieldInfo) or node.ref.kind != "const"
    if isinstance(node, FieldAccessNode):
        return addressable(node.object)
    return False


def has_call(node):
    """Whether evaluating node runs a function, which may change an object."""
    return any(isinstance(item, (CallNode, MemberCallNode)) for item in walk(node))


def generate(program, info):
    """Return the LLVM module for a checked program as text."""
    return CodeGenerator(info).generate(program)
