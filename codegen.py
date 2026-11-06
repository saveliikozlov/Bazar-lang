"""Bazar code generation: LLVM IR through the llvmlite.ir builder.

    generate(program, info) -> str

Runs after semantic.analyze(), whose annotations it reads: every expression
has .type, names have .ref, calls have .target, field accesses .field_info.
The only IR text the compiler writes is str(module), printed by llvmlite.

Layout of the module:
* an identified struct type "bz.T" per structure, fields in field order, an
  LLVM array type [N x T] per Bazar array type, {i1, T} per може T, and
  {i1, T, E} per вийде T або облом E, whose tag is 1 for шось and вийшло;
* "bz.NAME" per function and "bz.T.NAME" per member function, whose first
  parameter is a pointer to the object; the prefix keeps a function named
  main or printf apart from the C runtime;
* "main", the top-level statements;
* printf, scanf, write and exit declared without bodies; clang links them
  against the C library, and llvm.memcpy once an object is copied;
* format strings and string literals as private global constants.

Every variable lives in a slot made in its function's entry block: an alloca,
or, for a value of HEAP_THRESHOLD bytes or more, memory from bazar.alloc
that is freed before every ret, so large arrays never exhaust the stack. A scalar
(integer or базар) is an SSA value. An object (an aggregate) is never loaded
or stored as a whole, because LLVM compiles large aggregate values in
superlinear time: it stays in memory, and its value is copied with
llvm.memcpy. pointer() gives the memory of an object, emit_into() writes an
object's value straight into memory that the expression cannot see, and
snapshot() copies it into a fresh temporary. An object parameter is a pointer
that the callee only reads; an object result is written through a hidden first
parameter that points to memory of the caller.

Arithmetic uses the *.with.overflow intrinsics; an overflow, a division by
zero, MIN ділити на мінус 1, or an array index out of range writes one line to
stderr and exits with 1. Code that walks an array (filling, printing,
comparing, крутимось … з) is a loop at run time, never unrolled. розбери tests
its arms in order, each pattern against the value in memory, and falls to the
next arm on the first part that does not match.
"""

from llvmlite import ir
import llvmlite.binding as llvm

from ast_nodes import (
    ArrayFillNode, ArrayLiteralNode, AssignmentNode, BinaryNode, BindingPatternNode, BooleanNode, BreakNode,
    CallNode, CallStatementNode, DeclarationNode, ExitNode, FieldAccessNode, FieldAssignmentNode, ForEachNode,
    ForNode, IdentifierNode, IfNode, IndexNode, IntegerNode, InterpolationNode, LiteralPatternNode, MatchNode,
    MemberCallNode, NewObjectNode, PrintNode, ReadNode, ReturnNode, StringNode, StructurePatternNode, TryNode,
    UnaryNode, VariantNode, VariantPatternNode, WhileNode, WildcardPatternNode, walk,
)
from bazar_types import (
    ArrayType, BoolType, IntType, is_aggregate, is_scalar, is_variant, OptionType, payloads, ResultType,
    StructType,
)
from semantic import FieldInfo, is_name_chain

I1, I8, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(32), ir.IntType(64)
I8_PTR = I8.as_pointer()
INT_LLTYPES = {32: I32, 64: I64}         # IntType.bits -> LLVM type
INT_FORMATS = {32: "%d", 64: "%lld"}     # IntType.bits -> printf and scanf format
COMPARISONS = {"eq": "==", "ne": "!=", "gt": ">", "lt": "<"}
OVERFLOW_WORDS = {"add": "плюс", "sub": "мінус", "mul": "на"}
EXIT_MESSAGE = "Всьо, розходимось: %lld\n"
HEAP_THRESHOLD = 1024                    # bytes: a slot this large lives on the heap
OUT_OF_MEMORY = "помилка виконання: не вистачило пам'яті на масив чи об'єкт\n"


class CodeGenerator:
    def __init__(self, info):
        self.info = info
        self.module = ir.Module(name="bazar")
        self.module.triple = llvm.get_default_triple()
        self.strings = {}                    # text -> global constant
        self.struct_types = {}
        self.functions = {}                  # FunctionInfo -> ir.Function
        self.memcpy_function = None          # declared on the first copy of an object
        self.runtime = {}                    # name -> C function declared on first use
        self.alloc_function = None           # bazar.alloc, defined on the first heap slot
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
        if isinstance(t, ArrayType):
            return ir.ArrayType(self.lltype(t.element), t.length)
        if is_variant(t):
            return ir.LiteralStructType([I1] + [self.lltype(inner) for inner in payloads(t)])
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

    def c_function(self, name, result, parameters):
        """A C library function, declared the first time it is used."""
        if name not in self.runtime:
            self.runtime[name] = ir.Function(self.module, ir.FunctionType(result, parameters), name=name)
        return self.runtime[name]

    def flush(self, builder):
        """fflush(NULL): what printf holds back reaches stdout before anything goes to stderr."""
        builder.call(self.c_function("fflush", I32, [I8_PTR]), [ir.Constant(I8_PTR, None)])

    def allocator(self):
        """bazar.alloc(size): malloc, or a run-time error when memory runs out.

        The name has no "bz." prefix, so no Bazar function can take it."""
        if self.alloc_function is None:
            function = ir.Function(self.module, ir.FunctionType(I8_PTR, [I64]), name="bazar.alloc")
            function.linkage = "internal"
            builder = ir.IRBuilder(function.append_basic_block("entry"))
            memory = builder.call(self.c_function("malloc", I8_PTR, [I64]), [function.args[0]])
            failed = function.append_basic_block("failed")
            done = function.append_basic_block("done")
            builder.cbranch(builder.icmp_unsigned("==", memory, ir.Constant(I8_PTR, None)), failed, done)
            builder.position_at_end(failed)
            self.flush(builder)
            builder.call(self.write, [ir.Constant(I32, 2), self.string(OUT_OF_MEMORY),
                                      ir.Constant(I64, len(OUT_OF_MEMORY.encode("utf-8")))])
            builder.call(self.exit, [ir.Constant(I32, 1)])
            builder.unreachable()
            builder.position_at_end(done)
            builder.ret(memory)
            self.alloc_function = function
        return self.alloc_function

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
        self.heap = []                       # memory of the large slots, freed before every ret
        self.result_pointer = None           # where тримай writes an object result
        self.structure = None

    def finish_function(self):
        # Every way out of the function frees its large slots: тримай, ?, and the end.
        if self.heap:
            free = self.c_function("free", ir.VoidType(), [I8_PTR])
            for block in self.function.blocks:
                if isinstance(block.terminator, ir.Ret):      # ret and ret void alike
                    builder = ir.IRBuilder(block)
                    builder.position_before(block.terminator)
                    for memory in self.heap:
                        builder.call(free, [memory])
        ir.IRBuilder(self.entry).branch(self.function.blocks[1])

    def alloca(self, llvm_type, name=""):
        """A slot in the entry block: on the stack, or on the heap when it is large."""
        builder = ir.IRBuilder(self.entry)
        if byte_size(llvm_type) < HEAP_THRESHOLD:
            return builder.alloca(llvm_type, name=name)
        size = ir.Constant(llvm_type.as_pointer(), None).gep([ir.Constant(I32, 1)]).ptrtoint(I64)
        memory = builder.call(self.allocator(), [size])
        self.heap.append(memory)
        return builder.bitcast(memory, llvm_type.as_pointer(), name=name)

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
        elif isinstance(node, ForEachNode):
            self.for_each_statement(node)
        elif isinstance(node, MatchNode):
            self.match_statement(node)
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

    def for_each_statement(self, node):
        # The array is evaluated once. The counter is the element itself, read
        # in place: it cannot be assigned, and the array is a snapshot whenever
        # the body could change the original.
        if addressable(node.array) and not changes_objects(node.body):
            array = self.pointer(node.array)
        else:
            array = self.snapshot(node.array)
        length = ir.Constant(I64, node.array.type.length)
        slot = self.alloca(I64, node.name + ".номер")
        self.builder.store(ir.Constant(I64, 0), slot)
        body_block = self.new_block("each.body")
        step_block = self.new_block("each.step")
        end_block = self.new_block("each.end")
        self.builder.branch(body_block)
        self.builder.position_at_end(body_block)
        self.slots[node.info] = self.builder.gep(array, [ir.Constant(I32, 0), self.builder.load(slot)],
                                                 name=node.name)
        self.loop_body(node.body, end_block, step_block)
        self.builder.position_at_end(step_block)
        following = self.builder.add(self.builder.load(slot), ir.Constant(I64, 1))
        self.builder.store(following, slot)
        self.builder.cbranch(self.builder.icmp_signed("==", following, length), end_block, body_block)
        self.builder.position_at_end(end_block)

    def match_statement(self, node):
        # The value is evaluated once into memory. A name or a field is read in
        # place unless a guard could change it while the arms are tried; the
        # names of an arm are copies, so its body cannot change what it matched.
        subject_type = node.subject.type
        if not is_aggregate(subject_type):
            subject = self.alloca(self.lltype(subject_type))
            self.builder.store(self.value(node.subject), subject)
        elif addressable(node.subject) and not any(arm.guard is not None and changes_objects(arm.guard)
                                                   for arm in node.arms):
            subject = self.pointer(node.subject)
        else:
            subject = self.snapshot(node.subject)
        end_block = self.new_block("match.end")
        for arm in node.arms:
            next_block = self.new_block("match.next")
            self.test_pattern(arm.pattern, subject, next_block)
            if arm.guard is not None:
                body_block = self.new_block("match.body")
                self.builder.cbranch(self.value(arm.guard), body_block, next_block)
                self.builder.position_at_end(body_block)
            self.statements(arm.body.statements)
            if not self.builder.block.is_terminated:
                self.builder.branch(end_block)
            self.builder.position_at_end(next_block)
        self.builder.unreachable()           # some arm always matches (semantic rule 44)
        self.builder.position_at_end(end_block)

    def test_pattern(self, pattern, pointer, fail_block):
        """Continue at the current position if the value at pointer matches, else go to fail_block."""
        t = pattern.type
        if isinstance(pattern, WildcardPatternNode):
            return
        if isinstance(pattern, BindingPatternNode):
            slot = self.alloca(self.lltype(t), pattern.name)
            if is_aggregate(t):
                self.copy(slot, pointer, t)
            else:
                self.builder.store(self.builder.load(pointer), slot)
            self.slots[pattern.info] = slot
            return
        if isinstance(pattern, LiteralPatternNode):
            expected = ir.Constant(self.lltype(t), int(pattern.value))
            self.continue_if(self.builder.icmp_signed("==", self.builder.load(pointer), expected), fail_block)
            return
        if isinstance(pattern, VariantPatternNode):
            tag = self.builder.load(self.element(pointer, 0))
            held = pattern.variant in ("some", "ok")
            self.continue_if(tag if held else self.builder.not_(tag), fail_block)
            if pattern.inner is not None:
                self.test_pattern(pattern.inner, self.element(pointer, 1 if held else 2), fail_block)
            return
        if isinstance(pattern, StructurePatternNode):
            for index, field_pattern in enumerate(pattern.fields):
                self.test_pattern(field_pattern, self.element(pointer, index), fail_block)
            return
        # OrPatternNode: the first alternative that matches wins.
        matched_block = self.new_block("pattern.matched")
        for alternative in pattern.alternatives[:-1]:
            next_block = self.new_block("pattern.next")
            self.test_pattern(alternative, pointer, next_block)
            self.builder.branch(matched_block)
            self.builder.position_at_end(next_block)
        self.test_pattern(pattern.alternatives[-1], pointer, fail_block)
        self.builder.branch(matched_block)
        self.builder.position_at_end(matched_block)

    def continue_if(self, condition, fail_block):
        ok_block = self.new_block("pattern.ok")
        self.builder.cbranch(condition, ok_block, fail_block)
        self.builder.position_at_end(ok_block)

    def counted_loop(self, start, stop, body):
        """Run body(index) for every i64 index from start to stop - 1; nothing when start >= stop."""
        if start >= stop:
            return
        slot = self.alloca(I64)
        self.builder.store(ir.Constant(I64, start), slot)
        body_block = self.new_block("loop.body")
        end_block = self.new_block("loop.end")
        self.builder.branch(body_block)
        self.builder.position_at_end(body_block)
        index = self.builder.load(slot)
        body(index)
        following = self.builder.add(index, ir.Constant(I64, 1))
        self.builder.store(following, slot)
        done = self.builder.icmp_signed("==", following, ir.Constant(I64, stop))
        self.builder.cbranch(done, end_block, body_block)
        self.builder.position_at_end(end_block)

    # -------------------------------------------------------------- print

    def print_statement(self, node):
        if isinstance(node, StringNode):
            self.builder.call(self.printf, [self.string("%s\n"), self.string(node.value)])
            return
        if isinstance(node, InterpolationNode):
            # Each value runs just before it is printed, with the text in front of it.
            text = ""
            for part in node.parts:
                if isinstance(part, StringNode):
                    text += part.value
                else:
                    self.print_value(self.operand(part), part.type, text, "")
                    text = ""
            self.builder.call(self.printf, [self.string("%s\n"), self.string(text)])
            return
        self.print_value(self.operand(node), node.type, "", "\n")

    def print_value(self, value, t, prefix, suffix):
        """printf prefix, the value, and suffix; objects walk their field table.

        value is an SSA value for a scalar and a pointer for an object. prefix
        and suffix are plain text: a % in them is escaped wherever they become
        part of a printf format."""
        if isinstance(t, IntType):
            self.builder.call(self.printf, [self.string(literal(prefix) + INT_FORMATS[t.bits] + literal(suffix)),
                                            value])
        elif isinstance(t, BoolType):
            text = self.builder.select(value, self.string("реально"), self.string("гон"))
            self.builder.call(self.printf, [self.string(literal(prefix) + "%s" + literal(suffix)), text])
        elif isinstance(t, StructType):
            structure = self.info.structures[t.name]
            opening = f"{prefix}{t.name} {{"
            fields = list(structure.fields.values())
            if not fields:
                self.builder.call(self.printf, [self.string(literal(opening + "}" + suffix))])
                return
            for number, field in enumerate(fields):
                pointer = self.element(value, field.index)
                field_value = pointer if is_aggregate(field.type) else self.builder.load(pointer)
                separator = opening + " " if number == 0 else ", "
                closing = " }" + suffix if number == len(fields) - 1 else ""
                self.print_value(field_value, field.type, f"{separator}{field.name}: ", closing)
        elif is_variant(t):
            # шось(x) or нема; вийшло(x) or облом(e).
            words = ("шось", "нема") if isinstance(t, OptionType) else ("вийшло", "облом")
            held_block = self.new_block("print.held")
            other_block = self.new_block("print.other")
            end_block = self.new_block("print.end")
            self.builder.cbranch(self.builder.load(self.element(value, 0)), held_block, other_block)
            for block, index, word in ((held_block, 1, words[0]), (other_block, 2, words[1])):
                self.builder.position_at_end(block)
                if index < len(payloads(t)) + 1:
                    inner = payloads(t)[index - 1]
                    self.print_value(self.operand_at(self.element(value, index), inner), inner,
                                     f"{prefix}{word}(", ")" + suffix)
                else:
                    self.builder.call(self.printf, [self.string("%s"), self.string(prefix + word + suffix)])
                self.builder.branch(end_block)
            self.builder.position_at_end(end_block)
        elif isinstance(t, ArrayType):
            # [a, b, c]: the first element, then a loop over the rest with ", " before each.
            def show(index, element_prefix, element_suffix):
                pointer = self.builder.gep(value, [ir.Constant(I32, 0), index])
                element = pointer if is_aggregate(t.element) else self.builder.load(pointer)
                self.print_value(element, t.element, element_prefix, element_suffix)

            closing = "]" + suffix
            show(ir.Constant(I64, 0), prefix + "[", closing if t.length == 1 else "")
            if t.length > 1:
                self.counted_loop(1, t.length, lambda index: show(index, ", ", ""))
                self.builder.call(self.printf, [self.string("%s"), self.string(closing)])
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
        if isinstance(node, FieldAccessNode) and getattr(node, "variant", None):
            # з.шось and the others read the tag.
            tag = self.builder.load(self.element(self.pointer(node.object), 0))
            return tag if node.variant in ("some", "ok") else self.builder.not_(tag)
        if isinstance(node, FieldAccessNode) and node.field_info is None:
            # розмір of an array is known now; the array still runs if it is more than a name.
            if not is_name_chain(node.object):
                self.pointer(node.object)
            return ir.Constant(self.lltype(node.type), node.length)
        if isinstance(node, FieldAccessNode):
            return self.builder.load(self.pointer(node), name=node.field)
        if isinstance(node, IndexNode):
            return self.builder.load(self.pointer(node))
        if isinstance(node, TryNode):
            return self.builder.load(self.unwrap(node))
        if isinstance(node, (CallNode, MemberCallNode)):
            return self.call(node, None)
        raise AssertionError(f"no scalar code for {type(node).__name__}")

    def operand(self, node):
        """An SSA value for a scalar expression, a pointer for an object."""
        return self.pointer(node) if is_aggregate(node.type) else self.value(node)

    def operand_at(self, pointer, t):
        """What is stored at pointer, as operand() gives it: loaded for a scalar."""
        return pointer if is_aggregate(t) else self.builder.load(pointer)

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
        if isinstance(node, IndexNode):
            array = self.pointer(node.object)
            return self.builder.gep(array, [ir.Constant(I32, 0), self.checked_index(node)])
        if isinstance(node, TryNode):
            return self.unwrap(node)
        return self.snapshot(node)

    def unwrap(self, node):
        """з?: a pointer to what шось or вийшло holds, after the tag says it holds one.

        Otherwise a function writes нема, or облом with its error, to its
        result and returns; the main program stops with a run-time error."""
        held_type = node.operand.type
        container = self.pointer(node.operand)
        held_block = self.new_block("try.held")
        other_block = self.new_block("try.other")
        self.builder.cbranch(self.builder.load(self.element(container, 0)), held_block, other_block)
        self.builder.position_at_end(other_block)
        if self.result_pointer is None:
            # Only the main program: the semantic pass allows ? in a function
            # only when its result is може or вийде, which has a result pointer.
            got, wanted = ("нема", "шось") if isinstance(held_type, OptionType) else ("облом", "вийшло")
            self.stop(node, f"«?» отримав «{got}» замість «{wanted}»")
        else:
            self.builder.store(ir.Constant(I1, 0), self.element(self.result_pointer, 0))
            if isinstance(held_type, ResultType):
                self.copy(self.element(self.result_pointer, 2), self.element(container, 2), held_type.error)
            self.builder.ret_void()
        self.builder.position_at_end(held_block)
        return self.element(container, 1)

    def checked_index(self, node):
        """The index as i64; one unknown before the run is compared with the length.

        An unsigned comparison catches a negative index too."""
        index = self.value(node.index)
        if index.type != I64:
            index = self.builder.sext(index, I64)
        length = node.object.type.length
        if node.index_value is None:
            self.fail_if(self.builder.icmp_unsigned(">=", index, ir.Constant(I64, length)), node.index,
                         f"номер за межами масиву: тут можна від 0 до {length - 1}")
        return index

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
        elif isinstance(node, ArrayLiteralNode):
            for index, item in enumerate(node.elements):
                self.store_value(self.element(destination, index), item)
        elif isinstance(node, ArrayFillNode):
            self.fill(destination, node)
        elif isinstance(node, VariantNode):
            # The tag, then the value in its own place: шось and вийшло at 1, облом at 2.
            held = node.variant in ("some", "ok")
            self.builder.store(ir.Constant(I1, int(held)), self.element(destination, 0))
            if node.value is not None:
                self.store_value(self.element(destination, 1 if held else 2), node.value)
        elif isinstance(node, BinaryNode):
            self.fallback(node, destination)
        else:
            self.copy(destination, self.pointer(node), node.type)

    def store_value(self, pointer, node):
        """Write the value of any expression to memory that node cannot see."""
        if is_aggregate(node.type):
            self.emit_into(pointer, node)
        else:
            self.builder.store(self.value(node), pointer)

    def fill(self, destination, node):
        """[всюди x]: x runs once and goes to element 0, which a loop copies to the rest."""
        element_type = node.type.element
        first = self.element(destination, 0)
        if is_aggregate(element_type):
            self.emit_into(first, node.value)

            def put(index):
                self.copy(self.builder.gep(destination, [ir.Constant(I32, 0), index]), first, element_type)
        else:
            value = self.value(node.value)
            self.builder.store(value, first)

            def put(index):
                self.builder.store(value, self.builder.gep(destination, [ir.Constant(I32, 0), index]))
        self.counted_loop(1, node.type.length, put)

    def build_object(self, destination, node):
        """склепай: the given values in field order, then the defaults of the fields left out."""
        for field in self.info.structures[node.structure].fields.values():
            pointer = self.element(destination, field.index)
            if field.index >= len(node.arguments):
                self.store_default(pointer, field)
            else:
                self.store_value(pointer, node.arguments[field.index])

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
        if getattr(node, "fallback", False):
            return self.fallback(node, None)
        if operator in ("and", "or"):
            return self.short_circuit(node)
        if is_aggregate(node.left.type):
            return self.aggregate_comparison(node)
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

    def fallback(self, node, destination):
        """з або x: what з holds, or x, which runs only when з holds нема or облом.

        A scalar result is a phi; an object result is written to destination."""
        container = self.pointer(node.left)
        held_block = self.new_block("fallback.held")
        other_block = self.new_block("fallback.other")
        end_block = self.new_block("fallback.end")
        self.builder.cbranch(self.builder.load(self.element(container, 0)), held_block, other_block)
        self.builder.position_at_end(held_block)
        held = self.element(container, 1)
        if destination is None:
            held = self.builder.load(held)
        else:
            self.copy(destination, held, node.type)
        held_end = self.builder.block
        self.builder.branch(end_block)
        self.builder.position_at_end(other_block)
        if destination is None:
            other = self.value(node.right)
        else:
            self.emit_into(destination, node.right)
        other_end = self.builder.block
        self.builder.branch(end_block)
        self.builder.position_at_end(end_block)
        if destination is not None:
            return None
        result = self.builder.phi(self.lltype(node.type))
        result.add_incoming(held, held_end)
        result.add_incoming(other, other_end)
        return result

    def aggregate_comparison(self, node):
        """рівно and не рівно on arrays, може, and вийде: part by part.

        Not memcmp: LLVM leaves the unused bits of a stored базар unspecified,
        and нема holds no value at all. A borrowed left side is a snapshot when
        the right side may change it."""
        if addressable(node.left) and has_call(node.right):
            left = self.snapshot(node.left)
        else:
            left = self.pointer(node.left)
        same = self.equal(left, self.pointer(node.right), node.left.type)
        return same if node.operator == "eq" else self.builder.not_(same)

    def equal(self, left, right, t):
        if is_scalar(t):
            return self.builder.icmp_signed("==", self.builder.load(left), self.builder.load(right))
        if is_variant(t):
            return self.equal_variants(left, right, t)
        result = self.alloca(I1)
        self.builder.store(ir.Constant(I1, 1), result)

        def compare(index):
            same = self.equal(self.builder.gep(left, [ir.Constant(I32, 0), index]),
                              self.builder.gep(right, [ir.Constant(I32, 0), index]), t.element)
            self.builder.store(self.builder.and_(self.builder.load(result), same), result)
        self.counted_loop(0, t.length, compare)
        return self.builder.load(result)

    def equal_variants(self, left, right, t):
        """Equal tags, and then equal values: шось and вийшло at 1, облом at 2; нема holds none."""
        result = self.alloca(I1)
        left_tag = self.builder.load(self.element(left, 0))
        same_tag = self.builder.icmp_signed("==", left_tag, self.builder.load(self.element(right, 0)))
        self.builder.store(same_tag, result)
        tag_block = self.new_block("same.tag")
        held_block = self.new_block("same.held")
        other_block = self.new_block("same.other")
        end_block = self.new_block("same.end")
        self.builder.cbranch(same_tag, tag_block, end_block)
        self.builder.position_at_end(tag_block)
        self.builder.cbranch(left_tag, held_block, other_block)
        for block, index in ((held_block, 1), (other_block, 2)):
            self.builder.position_at_end(block)
            if index <= len(payloads(t)):
                inner = payloads(t)[index - 1]
                self.builder.store(self.equal(self.element(left, index), self.element(right, index), inner),
                                   result)
            self.builder.branch(end_block)
        self.builder.position_at_end(end_block)
        return self.builder.load(result)

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
        self.stop(node, message)
        self.builder.position_at_end(ok_block)

    def stop(self, node, message):
        """Write one run-time error line for node to stderr and exit with 1; ends the block."""
        text = f"помилка виконання: line {node.line}:{node.column}: {message}\n"
        self.flush(self.builder)
        self.builder.call(self.write, [ir.Constant(I32, 2), self.string(text),
                                       ir.Constant(I64, len(text.encode("utf-8")))])
        self.builder.call(self.exit, [ir.Constant(I32, 1)])
        self.builder.unreachable()

    # ---------------------------------------------------------- addresses

    def name_address(self, info):
        if isinstance(info, FieldInfo):          # a field of the own object, inside a member function
            return self.element(self.self_pointer, info.index, info.name)
        return self.slots[info]


def byte_size(llvm_type):
    """About how many bytes a value of llvm_type takes, padding aside: enough to pick its slot."""
    if isinstance(llvm_type, ir.IntType):
        return max(1, (llvm_type.width + 7) // 8)
    if isinstance(llvm_type, ir.ArrayType):
        return llvm_type.count * byte_size(llvm_type.element)
    if isinstance(llvm_type, (ir.LiteralStructType, ir.IdentifiedStructType)):
        return sum(byte_size(element) for element in llvm_type.elements)
    return 8


def literal(text):
    """Text that printf prints as it is, when it stands in a format."""
    return text.replace("%", "%%")


def addressable(node):
    """A chain of names and fields that lives in memory, not a temporary."""
    if isinstance(node, IdentifierNode):
        return isinstance(node.ref, FieldInfo) or node.ref.kind != "const"
    if isinstance(node, (FieldAccessNode, IndexNode)):
        return addressable(node.object)
    return False


def changes_objects(node):
    """Whether running node may change memory that already exists: a call or an assignment."""
    return any(isinstance(item, (CallNode, MemberCallNode, AssignmentNode, FieldAssignmentNode))
               for item in walk(node))


def has_call(node):
    """Whether evaluating node runs a function, which may change an object."""
    return any(isinstance(item, (CallNode, MemberCallNode)) for item in walk(node))


def generate(program, info):
    """Return the LLVM module for a checked program as text."""
    return CodeGenerator(info).generate(program)
