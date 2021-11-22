import os
os.environ["PATH"] += os.pathsep + 'D:\\Bibliotecas\\graphviz-2.44.1-win32\\Graphviz\\bin'

from graphviz import Digraph

def format_instruction(t):
    operand = t[0].split("_")
    op = operand[0]
    ty = operand[1] if len(operand) > 1 else None
    if len(operand) >= 3:
        for _qual in operand[2:]:
            if _qual == "*":
                ty += "*"
            else:
                ty += f"[{_qual}]"
    if len(t) > 1:
        if op == "define":
            return (
                f"\n{op} {ty} {t[1]} ("
                + ", ".join(list(" ".join(el) for el in t[2]))
                + ")"
            )
        else:
            _str = "" if op == "global" else "  "
            if op == "jump":
                _str += f"{op} label {t[1]}"
            elif op == "cbranch":
                _str += f"{op} {t[1]} label {t[2]} label {t[3]}"
            elif op == "global":
                if ty.startswith("string"):
                    _str += f"{t[1]} = {op} {ty} '{t[2]}'"
                elif len(t) > 2:
                    _str += f"{t[1]} = {op} {ty} {t[2]}"
                else:
                    _str += f"{t[1]} = {op} {ty}"
            elif op == "return" or op == "print":
                _str += f"{op} {ty} {t[1]}"
            elif op == "sitofp" or op == "fptosi":
                _str += f"{t[2]} = {op} {t[1]}"
            elif op == "store" or op == "param":
                _str += f"{op} {ty} "
                for _el in t[1:]:
                    _str += f"{_el} "
            else:
                _str += f"{t[-1]} = {op} {ty} "
                for _el in t[1:-1]:
                    _str += f"{_el} "
            return _str
    elif ty == "void":
        return f"  {op}"
    else:
        return f"{op}"


class Block:
    def __init__(self, label):
        self.label = label  # Label that identifies the block
        self.instructions = []  # Instructions in the block
        self.predecessors = []  # List of predecessors
        self.next_block = None  # Link to the next block

        self.numerated_code = {}

        self.defs = {}

        self.gen_defs = []
        self.kill_defs = []
        self.in_RD = []
        self.out_RD = []

        self.used = []
        self.defined = []
        self.in_set = []
        self.out_set = []

    def append(self, instr):
        self.instructions.append(instr)

    def __iter__(self):
        return iter(self.instructions)


class BasicBlock(Block):
    """
    Class for a simple basic block.  Control flow unconditionally
    flows to the next block.
    """

    def __init__(self, label):
        super(BasicBlock, self).__init__(label)
        self.branch = None  # Not necessary the same as next_block in the linked list


class ConditionBlock(Block):
    """
    Class for a block representing an conditional statement.
    There are two branches to handle each possibility.
    """

    def __init__(self, label):
        super(ConditionBlock, self).__init__(label)
        self.taken = None
        self.fall_through = None

class BlockVisitor(object):
    def visit(self, block):
        while isinstance(block, Block):
            name = "visit_%s" % type(block).__name__
            if hasattr(self, name):
                getattr(self, name)(block)
            block = block.next_block

class EmitBlocks(BlockVisitor):
    def __init__(self):
        self.code = []

    def visit_BasicBlock(self, block):
        for inst in block.instructions:
            self.code.append(inst)

    def visit_ConditionBlock(self, block):
        for inst in block.instructions:
            self.code.append(inst)


class CFG:
    def __init__(self, fname):
        self.fname = fname
        self.g = Digraph("g", filename=fname + ".gv", node_attr={"shape": "record"})

    def visit_BasicBlock(self, block):
        # Get the label as node name
        _name = block.label
        if _name:
            # get the formatted instructions as node label
            _label = "{" + _name + ":\\l\t"
            for _inst in block.instructions[1:]:
                _label += format_instruction(_inst) + "\\l\t"
            _label += "}"
            self.g.node(_name, label=_label)
            if block.branch:
                self.g.edge(_name, block.branch.label)
        else:
            # Function definition. An empty block that connect to the Entry Block
            self.g.node(self.fname, label=None, _attributes={"shape": "ellipse"})
            self.g.edge(self.fname, block.next_block.label)

    def visit_ConditionBlock(self, block):
        # Get the label as node name
        _name = block.label
        # get the formatted instructions as node label
        _label = "{" + _name + ":\\l\t"
        for _inst in block.instructions[1:]:
            _label += format_instruction(_inst) + "\\l\t"
        _label += "|{<f0>T|<f1>F}}"
        self.g.node(_name, label=_label)
        self.g.edge(_name + ":f0", block.taken.label)
        self.g.edge(_name + ":f1", block.fall_through.label)

    def view(self, block):
        while isinstance(block, Block):
            name = "visit_%s" % type(block).__name__
            if hasattr(self, name):
                getattr(self, name)(block)
            block = block.next_block
        # You can use the next stmt to see the dot file
        #print(self.g.source)
        self.g.view()
