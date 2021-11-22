import argparse
import pathlib
import sys
import collections
from uc.uc_ast import FuncDef
from uc.uc_block import CFG, format_instruction, BasicBlock, ConditionBlock
from uc.uc_code import CodeGenerator
from uc.uc_interpreter import Interpreter
from uc.uc_parser import UCParser
from uc.uc_sema import NodeVisitor, Visitor

#Caio Augusto Alves Nolasco
#RA: 195181

binary_ops = [
    "add_",
    "sub_",
    "mul_",
    "div_",
    "mod_",
    "lt_",
    "le_",
    "gt_",
    "ge_",
    "eq_",
    "and_",
    "or_",
    "ne_",
]

class DataFlow(NodeVisitor):
    def __init__(self, viewcfg):
        # flag to show the optimized control flow graph
        self.viewcfg = viewcfg
        # list of code instructions after optimizations
        self.code = []
        # TODO

        self.global_variables = []
        self.dead_code = []

        self.labeled_code = {}
        self.defs = {}
        self.index = 1

    def show(self, buf=sys.stdout):
        _str = ""
        for _code in self.code:
            _str += format_instruction(_code) + "\n"
        buf.write(_str)

    # TODO: add analyses

    def add_to_defs(self, variable, index):
        if variable not in self.defs:
            self.defs[variable] = []
            self.defs[variable].append(index)
        else:
            self.defs[variable].append(index)

        #print(self.defs)

    def update_block_gen_kill_RD(self, block, inst_gen, inst_kill):

        if not inst_gen and not inst_kill:
            return

        if not block.gen_defs:
            block.gen_defs = inst_gen
            if not block.kill_defs:
                block.kill_defs = inst_kill
        else:
            block.gen_defs = [i for i in block.gen_defs if i not in inst_kill] + inst_gen
            block.kill_defs = block.kill_defs + inst_kill

    def find_exit_block(self, cfg):
        bb = cfg

        while bb is not None:
            if bb.label == "%exit":
                break
            bb = bb.next_block

        return bb

    def save_global_variables(self, node):
        for inst in node.text:
            self.global_variables.append(inst[1])

    def number_instructions(self, cfg):
        bb = cfg
        
        self.labeled_code = {}
        self.index = 1

        while bb is not None:
            for inst in bb.instructions:
                bb.numerated_code[self.index] = inst
                self.labeled_code[self.index] = inst
                if inst[0].startswith("literal"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("store"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("load"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("call"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("not_"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("sitofp"):
                    self.add_to_defs(inst[2], self.index)
                
                elif inst[0].startswith("fptosi"):
                    self.add_to_defs(inst[2], self.index)

                elif inst[0].startswith("elem"):
                    self.add_to_defs(inst[3], self.index)

                elif inst[0].startswith("define"):
                    parameter_list = inst[2]
                    for parameter in parameter_list:
                        self.add_to_defs(parameter[1], self.index)

                for bin_op in binary_ops:
                    if inst[0].startswith(bin_op):
                        self.add_to_defs(inst[3], self.index)                      

                self.index = self.index + 1

            bb = bb.next_block

    def instruction_gen_kill(self, inst, index):
        inst_gen = []
        inst_kill = []
        if inst[0].startswith("store"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
        elif inst[0].startswith("literal"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
        elif inst[0].startswith("load"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
        elif inst[0].startswith("call"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
        elif inst[0].startswith("not_"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)

        elif inst[0].startswith("sitofp"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
        elif inst[0].startswith("fptosi"):
            inst_gen = [index]
            inst_kill = self.defs[inst[2]].copy()
            inst_kill.remove(index)
                
        for bin_op in binary_ops:
            if inst[0].startswith(bin_op):
                inst_gen = [index]
                inst_kill = self.defs[inst[3]].copy()
                inst_kill.remove(index)
        
        return inst_gen, inst_kill

    def check_constant_propagation(self, current_defs, variable):
        if variable[0] == "@":
            return None

        if variable not in self.defs:
            return None

        current_value = None
        for definition in current_defs:
            if definition in self.defs[variable]:
                if self.labeled_code[definition][0].startswith("store"):
                    for store_defs in self.defs[self.labeled_code[definition][1]]:
                        if self.labeled_code[store_defs][0].startswith("literal"):
                            if current_value is None:
                                current_value = self.labeled_code[store_defs][1]
                            elif current_value != self.labeled_code[store_defs][1]:
                                current_value = None
                                break
                        else:
                            current_value = None
                            break
                else:
                    current_value = None
                    break

        return current_value
    
    def visit_Program(self, node):
        # First, save the global instructions on code member
        self.code = node.text[:]  # [:] to do a copy
        self.save_global_variables(node)

        for _decl in node.gdecls:
            if isinstance(_decl, FuncDef):

                # start with Reach Definitions Analysis
                self.defs = {}
                self.number_instructions(_decl.cfg)

                self.buildRD_blocks(_decl.cfg)
                self.computeRD_gen_kill(_decl.cfg)
                self.computeRD_in_out(_decl.cfg)
                # and do constant propagation optimization
                self.constant_propagation(_decl.cfg)

                #self.print_in_out(_decl.cfg)

                # after do live variable analysis
                #self.buildLV_blocks(_decl.cfg)
                exit_block = self.find_exit_block(_decl.cfg)
                self.computeLV_use_def(_decl.cfg)
                self.computeLV_in_out(exit_block, _decl.cfg)
                # and do dead code elimination
                self.deadcode_elimination(_decl.cfg)

                # after that do cfg simplify (optional)
                self.short_circuit_jumps(_decl.cfg)
                self.merge_blocks(_decl.cfg)
                self.discard_unused_allocs(_decl.cfg)

                # finally save optimized instructions in self.code
                self.appendOptimizedCode(_decl.cfg)

        if self.viewcfg:
            for _decl in node.gdecls:
                if isinstance(_decl, FuncDef):
                    dot = CFG(_decl.decl.name.name + ".opt")
                    dot.view(_decl.cfg)

    def buildRD_blocks(self, cfg):
        pass

    def computeRD_gen_kill(self, cfg):
        bb = cfg

        while bb is not None:
            for index, inst in bb.numerated_code.items():
                inst_gen, inst_kill = self.instruction_gen_kill(inst, index)

                self.update_block_gen_kill_RD(bb, inst_gen, inst_kill)

            bb = bb.next_block

    def computeRD_in_out(self, cfg):
        bb = cfg

        changed = []
        
        while bb is not None:
            changed.append(bb)
            bb=bb.next_block

        while changed:
            block = changed.pop(0)

            for pred in block.predecessors:
                block.in_RD = list(set(block.in_RD).union(pred.out_RD))

            old_out = block.out_RD

            block.out_RD = list(set([i for i in block.in_RD if i not in block.kill_defs]).union(block.gen_defs))

            if not (sorted(old_out) == sorted(block.out_RD)):
                if isinstance(block, BasicBlock):
                    if block.branch is not None:
                        changed.append(block.branch)
                    elif block.next_block is not None:
                        changed.append(block.next_block)
                elif isinstance(block, ConditionBlock):
                    changed.append(block.taken)
                    if block.fall_through is not None:
                        changed.append(block.fall_through)

    def print_in_out(self, cfg):
        bb = cfg
        while bb is not None:
            print(bb.label, bb.in_RD, bb.out_RD)
            bb = bb.next_block

    def constant_propagation(self, cfg):
        bb = cfg
        current_defs = bb.in_RD.copy()

        while bb is not None:
            current_defs = bb.in_RD.copy()
            for index, inst in bb.numerated_code.items():
                if inst[0].startswith("load"):
                    expr_value = self.check_constant_propagation(current_defs, inst[1])

                    if expr_value is not None:
                        bb.numerated_code[index] = ("literal_" + str(type(expr_value).__name__), expr_value, inst[2])
                        self.labeled_code[index] = bb.numerated_code[index]

                inst_gen, inst_kill = self.instruction_gen_kill(inst, index)

                if inst_gen or inst_kill:
                    current_defs = list(set([i for i in current_defs if i not in inst_kill]).union(inst_gen))

            bb = bb.next_block



    def buildLV_blocks(self, cfg):
        pass

    def computeLV_use_def(self, cfg):
        bb = cfg

        while bb is not None:
            for key, inst in bb.numerated_code.items():
                #defining instructions
                if inst[0].startswith("store"):
                    bb.used.append(inst[1])
                    bb.defined.append(inst[2])
                elif inst[0].startswith("literal"):
                    bb.defined.append(inst[2])
                elif inst[0].startswith("load"):
                    bb.used.append(inst[1])
                    bb.defined.append(inst[2])
                elif inst[0].startswith("call"):
                    bb.defined.append(inst[2])
                    bb.used.append(inst[1])
                elif inst[0].startswith("elem"):
                    bb.defined.append(inst[3])
                    bb.used.append(inst[1])
                    bb.used.append(inst[2]) 
                elif inst[0].startswith("not_"):
                    bb.defined.append(inst[2])
                    bb.used.append(inst[1])

                for bin_op in binary_ops:
                    if inst[0].startswith(bin_op):
                        bb.used.append(inst[1])
                        bb.used.append(inst[2])
                        bb.defined.append(inst[3])

                if inst[0].startswith("call"):
                    bb.defined.append(inst[2])

            

                #using instructions
                if inst[0].startswith("print"):
                    bb.used.append(inst[1])
                elif inst[0].startswith("sitofp"):
                    bb.used.append(inst[1])
                    bb.defined.append(inst[2])
                elif inst[0].startswith("fptosi"):
                    bb.used.append(inst[1])
                    bb.defined.append(inst[2])

                elif inst[0].startswith("return"):
                    if inst[0] != "return_void":
                        bb.used.append(inst[1])
                elif inst[0].startswith("param"):
                    bb.used.append(inst[1])
                elif inst[0].startswith("cbranch"):
                    bb.used.append(inst[1])

            bb.used = list(dict.fromkeys(bb.used))
            bb.defined = list(dict.fromkeys(bb.defined))

            bb = bb.next_block
        

    def computeLV_in_out(self, end_block, first_block):
        block = first_block
        worklist = []

        while block is not None:
            worklist.append(block)
            block = block.next_block

        while worklist:
            block = worklist.pop(-1)

            old_in = block.in_set
            old_out = block.out_set

            block.in_set = list(set([i for i in block.out_set if i not in block.defined]).union(block.used))

            if block.label == "%exit":
                block.out_set = self.global_variables
            elif isinstance(block, BasicBlock):
                if block.branch is not None:
                    block.out_set = block.branch.in_set
                else:
                    block.out_set = block.next_block.in_set
            elif isinstance(block, ConditionBlock):
                block.out_set = list(set(block.taken.in_set).union(block.fall_through.in_set))

            if not (sorted(old_out) == sorted(block.out_set) and sorted(old_in) == sorted(block.in_set)):
                #print(old_out, block.out_set, old_in, block.in_set)
                for pred in block.predecessors:
                    worklist.append(pred)

        temp_block = first_block
        while temp_block is not None:
            temp_block = temp_block.next_block            

    def deadcode_elimination(self, cfg):
        bb = cfg

        self.dead_code = []

        while bb is not None:
            for key, inst in bb.numerated_code.items():
                if inst[0].startswith("store"):
                    if inst[2] not in bb.out_set and inst[2] not in bb.used:
                        self.dead_code.append(key)
                elif inst[0].startswith("literal"):
                    if inst[2] not in bb.out_set and inst[2] not in bb.used:
                        self.dead_code.append(key)
                elif inst[0].startswith("load"):
                    if inst[2] not in bb.out_set and inst[2] not in bb.used:
                        self.dead_code.append(key)

                for bin_op in binary_ops:
                    if inst[0].startswith(bin_op):
                        if inst[3] not in bb.out_set and inst[3] not in bb.used:
                            self.dead_code.append(key)


                if inst[0].startswith("call"):
                    if inst[2] not in bb.out_set and inst[2] not in bb.used:
                        self.dead_code.append(key)

            bb = bb.next_block
        
    def short_circuit_jumps(self, cfg):
        pass
                     
    def merge_blocks(self, cfg):
        pass

    def discard_unused_allocs(self, cfg):
        pass

    def appendOptimizedCode(self, cfg):
        for key, inst in self.labeled_code.items():
            if key in self.dead_code:
                continue
            else:
                self.code.append(inst)


if __name__ == "__main__":

    # create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_file",
        help="Path to file to be used to generate uCIR. By default, this script runs the interpreter on the optimized uCIR \
              and shows the speedup obtained from comparing original uCIR with its optimized version.",
        type=str,
    )
    parser.add_argument(
        "--opt",
        help="Print optimized uCIR generated from input_file.",
        action="store_true",
    )
    parser.add_argument(
        "--speedup",
        help="Show speedup from comparing original uCIR with its optimized version.",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--debug", help="Run interpreter in debug mode.", action="store_true"
    )
    parser.add_argument(
        "-c",
        "--cfg",
        help="show the CFG of the optimized uCIR for each function in pdf format",
        action="store_true",
    )
    args = parser.parse_args()

    speedup = args.speedup
    print_opt_ir = args.opt
    create_cfg = args.cfg
    interpreter_debug = args.debug

    # get input path
    input_file = args.input_file
    input_path = pathlib.Path(input_file)

    # check if file exists
    if not input_path.exists():
        print("Input", input_path, "not found", file=sys.stderr)
        sys.exit(1)

    # set error function
    p = UCParser()
    # open file and parse it
    with open(input_path) as f:
        ast = p.parse(f.read())

    sema = Visitor()
    sema.visit(ast)

    gen = CodeGenerator(False)
    gen.visit(ast)
    gencode = gen.code

    opt = DataFlow(create_cfg)
    opt.visit(ast)
    optcode = opt.code
    if print_opt_ir:
        print("Optimized uCIR: --------")
        opt.show()
        print("------------------------\n")

    speedup = len(gencode) / len(optcode)
    sys.stderr.write(
        "[SPEEDUP] Default: %d Optimized: %d Speedup: %.2f\n\n"
        % (len(gencode), len(optcode), speedup)
    )

    vm = Interpreter(interpreter_debug)
    vm.run(optcode)
