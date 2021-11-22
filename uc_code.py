import argparse
import pathlib
import sys
from uc.uc_ast import FuncDef, FuncDecl, GlobalDecl, InitList, Constant, VarDecl, ArrayDecl, ExprList, ArrayRef, ID
from uc.uc_block import CFG, BasicBlock, ConditionBlock, format_instruction, EmitBlocks
from uc.uc_interpreter import Interpreter
from uc.uc_parser import UCParser
from uc.uc_sema import NodeVisitor, Visitor

binary_ops = {
    "+": "add",
    "-": "sub",
    "*": "mul",
    "/": "div",
    "%": "mod",
    "<": "lt",
    "<=": "le",
    ">": "gt",
    ">=": "ge",
    "==": "eq",
    "&&": "and",
    "||": "or",
    "!=": "ne",
}

unary_ops = {
    "!": "not",
    "-": "uminus",
    "+": "uplus",
}

class CodeGenerator(NodeVisitor):
    """
    Node visitor class that creates 3-address encoded instruction sequences
    with Basic Blocks & Control Flow Graph.
    """

    def __init__(self, viewcfg):
        self.viewcfg = viewcfg
        self.current_block = BasicBlock("%global")
        self.globals = []

        # version dictionary for temporaries. We use the name as a Key
        self.fname = "_glob_"
        self.versions = {self.fname: 0}

        # The generated code (list of tuples)
        # At the end of visit_program, we call each function definition to emit
        # the instructions inside basic blocks. The global instructions that
        # are stored in self.text are appended at beginning of the code
        self.code = []

        self.text = []  # Used for global declarations & constants (list, strings)

        self.var_dim = {} # armazena a dimensão das variáveis declaradas para uso no ArrayRef

        self.loop_pile = [] # pilha de loop, ultima posição equivale ao loop mais interno atual

    def show(self, buf=sys.stdout):
        _str = ""
        for _code in self.code:
            _str += format_instruction(_code) + "\n"
        buf.write(_str)

    def new_temp(self):
        """
        Create a new temporary variable of a given scope (function name).
        """
        if self.fname not in self.versions:
            self.versions[self.fname] = 1
        name = "%" + "%d" % (self.versions[self.fname])
        self.versions[self.fname] += 1
        return name

    def new_name(self, nm):
        name = nm

        if self.versions.get(name, 0) > 0:
            self.versions[name] += 1
            name = name + "." + "%d" % (self.versions[name])
        else:
            self.versions[name] = 1

        return name

    def new_text(self, typename):
        """
        Create a new literal constant on global section (text).
        """
        name = "@." + typename + "." + "%d" % (self.versions["_glob_"])
        self.versions["_glob_"] += 1
        return name

    def _get_origin(self, name):
        if name in self.globals:
            return "@"+name
        return "%"+name

    # dado um node de declaração mergulha no tipo do node até encontrar o nome da declaração
    def _get_name(self, node):
        aux = node
        if isinstance(aux, ArrayRef):
            while not isinstance(aux, ID):
                aux = aux.id
            name = aux.name
        else:
            while not hasattr(aux, 'declname'):
                aux = aux.type
            name = aux.declname.name
        return name

    # mergulha no type do node até encontrar o VarDecl e pegar o nome do tipo básico
    def _get_basic_type(self, node):
        aux = node
        while not isinstance(aux, VarDecl):
            aux = aux.type
        return aux.type.name

    # dado um node do tipo ArrayDecl ou InitList pega todas as suas dimensoes internas no formato _dim1_dim2_..._dimn
    # a implementacao permite que a ultima dimensao n seja especificada pelo usuario,
    # que deverá ser tratado com a dimensão do InitList provida pelo usuário
    def _get_dim(self, node):
        dim = ""
        aux = node
        while isinstance(aux, ArrayDecl):
            if aux.uc_type.size is not None:
                dim += "_" + str(aux.uc_type.size)
            else:
                dim += "_"

            aux = aux.type

        while isinstance(aux, InitList):
            dim += "_" + str(aux.size)
            aux = aux.decls[0]
        
        return dim

    # You must implement visit_Nodename methods for all of the other
    # AST nodes.  In your code, you will need to make instructions
    # and append them to the current block code list.
    #
    # A few sample methods follow. Do not hesitate to complete or change
    # them if needed.

    def visit_Program(self, node):
        # Visit all of the global declarations
        for _decl in node.gdecls:
            self.visit(_decl)

        # At the end of codegen, first init the self.code with
        # the list of global instructions allocated in self.text
        self.code = self.text.copy()
        # Also, copy the global instructions into the Program node
        node.text = self.text.copy()
        # After, visit all the function definitions and emit the
        # code stored inside basic blocks.
        for _decl in node.gdecls:
            if isinstance(_decl, FuncDef):
                # _decl.cfg contains the Control Flow Graph for the function
                # cfg points to start basic block
                bb = EmitBlocks()
                bb.visit(_decl.cfg)
                for _code in bb.code:
                    self.code.append(_code)

        if self.viewcfg:  # evaluate to True if -cfg flag is present in command line
            for _decl in node.gdecls:
                if isinstance(_decl, FuncDef):
                    dot = CFG(_decl.name.name.name)
                    dot.view(_decl.cfg)  # _decl.cfg contains the CFG for the function

    def visit_Constant(self, node):
        if node.type == "string":
            _target = self.new_text("str")
            inst = ("global_string", _target, node.value)
            self.text.append(inst)
        else:
            _target = self.new_temp()
            if node.type == 'int':
                value = int(node.value)
            elif node.type == 'float':
                value = float(node.value)
            else:
                value = node.value
            inst = ("literal_"+node.type, value, _target)
            self.current_block.append(inst)
        node.gen_location = _target

    def visit_BinaryOp(self, node):
        self.visit(node.left)
        self.visit(node.right)
        target = self.new_temp()
        opcode = binary_ops[node.op] + "_" + str(node.left.uc_type)
        inst = (opcode, node.left.gen_location, node.right.gen_location, target)
        self.current_block.append(inst)
        node.gen_location = target

    def visit_Print(self, node):
        # Visit the expression

        if isinstance(node.expr, ExprList):
            for _, child in node.expr.children():
                self.visit(child)
                typename = str(child.uc_type).split('[')[0]
                inst = ('print_'+typename, child.gen_location)
                self.current_block.append(inst)
        elif node.expr is not None:
            self.visit(node.expr)
            typename = str(node.expr.uc_type).split('[')[0]
            inst = ("print_"+typename, node.expr.gen_location)
            self.current_block.append(inst)
        else:
            nl = self.new_temp()
            inst = ("literal_char", "\n", nl)
            self.current_block.append(inst)
            inst = ("print_char", nl)
            self.current_block.append(inst)

    def visit_FuncDef(self, node):
        # inicializar blocos para construcao da CFG da função
        name = node.name.name.name
        node.cfg = BasicBlock("%"+name)

        if self.current_block is not None:
            node.cfg.predecessors.append(self.current_block)
            self.current_block.next_block = node.cfg
        self.current_block = node.cfg

        #atualiza o escopo
        self.fname = "_"+name+"_"

        typename = node.type.name

        # TODO visitar declaração dos argumentos
        # if isinstance(node.declaration, list):
        #     for item in node.declaration:
        #         self.visit(item)

        self.visit(node.name.type)
        params = node.name.type.text
        var_define = node.name.type.code

        inst = ('define_'+typename, '@'+name, params)
        node.cfg.append(inst)
        
        inst = ('entry',)
        node.cfg.append(inst)

        node.cfg.instructions += var_define

        # registrador com valor de retorno da função
        if typename != "void":
            target = self.new_temp()
            self.return_register = target
            inst = ('alloc_'+typename, target)
            node.cfg.append(inst)

        # visitar corpo da função
        self.visit(node.compound_statement)

        # jump para o bloco de retorno
        inst = ('jump', '%exit')
        self.current_block.append(inst)

        # setup do bloco de retorno e statement de retorno
        return_block = BasicBlock("%exit")
        return_block.predecessors.append(self.current_block)
        self.current_block.branch = return_block

        inst = ('exit:',)
        return_block.append(inst)

        if typename != "void":
            inst = ('return_'+typename, target)
        else:
            inst = ('return_void',)
        return_block.append(inst)

        self.current_block.next_block = return_block
        self.current_block.taken = return_block
        self.current_block = None

    def visit_FuncDecl(self, node):
        if node.param_list is not None:
            self.visit(node.param_list)
            node.text = node.param_list.text
            node.code = node.param_list.code
        else:
            node.text = []
            node.code = []

    def visit_ParamList(self, node):
        node.code = []
        node.text = []
        for decl in node.params:
            tgt = self.new_temp()
            typename = self._get_basic_type(decl)
            name = "%"+self._get_name(decl)

            inst = (typename, tgt)
            node.text.append(inst)

            inst = ("alloc_"+typename, name)
            node.code.append(inst)
            inst = ("store_"+typename, tgt, name)
            node.code.append(inst)
    
    def visit_GlobalDecl(self, node):
        for _, child in node.children():
            self.visit(child)

    def visit_Decl(self, node):
        node.type.init = node.init
        self.visit(node.type)

    def visit_VarDecl(self, node):
        _varname =  node.declname.name

        # se for apenas uma declaração sem inicialização
        if node.init is None:
            typename = node.type.name
            inst = ("alloc_"+typename+node.dim , "%"+_varname)
            self.current_block.append(inst)
            self.var_dim[_varname] = node.dim

        # declaracao com inicialização
        else:
            typename = str(node.init.uc_type).split('[')[0]

            # escopo global (GlobalDecl)
            if self.current_block.label == "%global":
                if isinstance(node.init, InitList):
                    self.visit(node.init)
                    value = node.init.code
                else:
                    value = node.init.value
                    if typename == 'int':
                        value = int(value)
                    elif typename == 'float':
                        value = float(value)

                if isinstance(node.init, InitList):
                    dim = self._get_dim(node.init)
                    inst = ("global_"+typename+dim, "@"+_varname, value)
                    self.var_dim[_varname] = dim
                else:
                    inst = ("global_"+typename, "@"+_varname, value)
                self.text.append(inst)
                self.globals.append(_varname)

            # escopo de função
            else:
                self.visit(node.init)

                if isinstance(node.init, InitList):
                    init_name = self.new_text(_varname)
                    dim = self._get_dim(node.init)
                    inst = ("alloc_"+typename+dim, "%"+_varname)
                    self.current_block.append(inst)
                    inst = ("global_"+typename+dim, init_name, node.init.code)
                    self.text.append(inst)
                    self.globals.append(init_name)
                    inst = ("store_"+typename+dim, init_name, "%"+_varname)
                    self.current_block.append(inst)
                    self.var_dim[_varname] = dim
                elif isinstance(node.init, Constant) and node.init.type == "string":
                    dim = "_" + str(len(node.init.value))
                    inst = ("alloc_"+typename+dim, "%"+_varname)
                    self.current_block.append(inst)
                    inst = ("store_"+typename+dim, node.init.gen_location, "%"+_varname)
                    self.current_block.append(inst)
                    self.var_dim[_varname] = dim                    
                else:
                    inst = ("alloc_"+typename, "%"+_varname)
                    self.current_block.append(inst)
                    inst = ("store_"+typename, node.init.gen_location, "%"+_varname)
                    self.current_block.append(inst)

    def visit_ArrayDecl(self, node):
        if node.init is not None:
            node.type.init = node.init
        else:
            # passar a dimensao do array para o VarDecl
            if node.dim == None:
                dim = self._get_dim(node)
                node.type.dim = dim
            else:
                node.type.dim = node.dim
        self.visit(node.type)      

    def visit_DeclList(self, node):
        # visitar todas as declarações
        for _, child in node.children():
            self.visit(child)

    def visit_Type(self, node):
        # não fazer nada
        pass

    # Statements: enquanto estiver movendo entre os blocos deve-se atualizar a referência para o bloco atual e seus antecessores

    def visit_If(self, node):
        # if
        if_name = self.new_name("if")
        if_block = ConditionBlock(if_name)

        # then
        then_name = self.new_name("then")
        then_block = BasicBlock(then_name)

        # se houver else criar
        if node.elsestat is not None:
            else_name = self.new_name("else")
            else_block = BasicBlock(else_name)

        # bloco para pular no final do if
        end_name = self.new_name("if.end")
        end_block = BasicBlock(end_name)

        # setup bloco if
        self.current_block.branch = if_block
        if_block.predecessors.append(self.current_block)

        inst = ("jump", "%"+if_name)
        self.current_block.append(inst)
        self.current_block.next_block = if_block
        self.current_block = if_block
        inst = (if_name+":",)
        if_block.append(inst)
        self.visit(node.expr)
        if node.elsestat is not None:
            inst = ("cbranch", node.expr.gen_location, "%"+then_name, "%"+else_name)
        else:
            inst = ("cbranch", node.expr.gen_location, "%"+then_name, "%"+end_name)
        self.current_block.append(inst)

        # setup do bloco then
        if_block.taken = then_block
        then_block.predecessors.append(self.current_block)

        self.current_block.next_block = then_block
        self.current_block = then_block
        inst = (then_name+":",)
        self.current_block.append(inst)
        self.visit(node.ifstat)
        inst = ("jump", "%"+end_name)
        self.current_block.append(inst)

        self.current_block.branch = end_block
        end_block.predecessors.append(self.current_block)

        # setup do bloco else
        if node.elsestat is not None:
            if_block.fall_through = else_block
            else_block.predecessors.append(if_block)

            self.current_block.next_block = else_block
            self.current_block = else_block
            inst = (else_name+":",)
            else_block.append(inst)
            self.visit(node.elsestat)
            inst = ("jump", "%"+end_name)
            self.current_block.append(inst)

            self.current_block.branch = end_block
            end_block.predecessors.append(self.current_block)
        else:
            if_block.fall_through = end_block

        # setup do bloco end
        self.current_block.next_block = end_block
        self.current_block = end_block

        inst = (end_name+":",)
        self.current_block.append(inst)


    def visit_For(self, node):        
        # 4 blocos: condição, incremento, statement, exit

        # condicao
        cond_name = self.new_name("for.cond")
        cond_block = ConditionBlock(cond_name)

        # corpo
        stat_name = self.new_name("for.stat")
        stat_block = BasicBlock(stat_name)

        # incremento
        inc_name = self.new_name("for.inc")
        inc_block = BasicBlock(inc_name)

        # end
        end_name = self.new_name("for.end")
        end_block = BasicBlock(end_name)

        # visitar inicializacao
        self.visit(node.t1)
        inst = ('jump', "%"+cond_name)
        self.current_block.append(inst)

        # setup da condicao
        self.current_block.branch = cond_block
        cond_block.predecessors.append(self.current_block)
        cond_block.predecessors.append(inc_block)
        cond_block.taken = stat_block
        cond_block.fall_through = end_block

        self.current_block.next_block = cond_block
        self.current_block = cond_block
        inst = (cond_name+":",)
        self.current_block.append(inst)
        self.visit(node.t2)
        inst = ("cbranch", node.t2.gen_location, "%"+stat_name, "%"+end_name)
        self.current_block.append(inst)

        # visitar o corpo do for
        stat_block.predecessors.append(cond_block)

        self.current_block.next_block = stat_block
        self.current_block = stat_block
        self.loop_pile.append(end_name)
        inst = (stat_name+":",)
        self.current_block.append(inst)
        self.visit(node.stat)
        inst = ("jump", "%"+inc_name)
        self.current_block.append(inst)
        self.loop_pile.pop(-1)

        self.current_block.branch = inc_block

        # visitar o incremento
        inc_block.predecessors.append(self.current_block)
        inc_block.branch = cond_block

        self.current_block.next_block = inc_block
        self.current_block = inc_block
        inst = (inc_name+":",)
        self.current_block.append(inst)
        self.visit(node.t3)
        inst = ("jump", "%"+cond_name)
        self.current_block.append(inst)

        # final do for
        end_block.predecessors.append(cond_block)

        self.current_block.next_block = end_block
        self.current_block = end_block
        inst = (end_name+":",)
        self.current_block.append(inst)

        # para printar o cfg
        cond_block.taken = stat_block
        cond_block.fall_through = end_block

    def visit_While(self, node):
        # 3 blocos: cond, stat e end

        # condicao
        cond_name = self.new_name("while.cond")
        cond_block = ConditionBlock(cond_name)

        # corpo do while
        stat_name = self.new_name("while.stat")
        stat_block = BasicBlock(stat_name)

        # end
        end_name = self.new_name("while.end")
        end_block = BasicBlock(end_name)

        # setup condicao
        cond_block.predecessors.append(self.current_block)
        cond_block.predecessors.append(stat_block)
        cond_block.taken = stat_block
        cond_block.fall_through = end_block
        self.current_block.branch = cond_block

        inst = ("jump", "%"+cond_name)
        self.current_block.append(inst)
        self.current_block.next_block = cond_block
        self.current_block = cond_block
        inst = (cond_name+":",)
        self.current_block.append(inst)
        self.visit(node.expr)
        inst = ("cbranch", node.expr.gen_location, "%"+stat_name, "%"+end_name)
        self.current_block.append(inst)

        # setup corpo
        stat_block.predecessors.append(cond_block)
        stat_block.branch = cond_block

        self.current_block.next_block = stat_block
        self.current_block = stat_block
        self.loop_pile.append(end_name)
        inst = (stat_name+":",)
        self.current_block.append(inst)
        self.visit(node.stat)
        inst = ("jump", "%"+cond_name)
        self.current_block.append(inst)
        self.loop_pile.pop(-1)

        # setup end
        end_block.predecessors.append(cond_block)

        self.current_block.next_block = end_block
        self.current_block = end_block
        inst = (end_name+":",)
        self.current_block.append(inst)

    def visit_Compound(self, node):
        # visitar as declarações e statements
        for _, child in node.children():
            self.visit(child)

    def visit_Assignment(self, node):
        self.visit(node.rvalue)

        if isinstance(node.lvalue, ID):  
            var = self._get_origin(node.lvalue.name)

            if node.op == "=":
                inst = ('store_'+str(node.rvalue.uc_type), node.rvalue.gen_location, var)
            else:
                self.visit(node.lvalue)
                inst = (binary_ops[node.op[0]]+"_"+str(node.rvalue.uc_type), node.lvalue.gen_location, node.rvalue.gen_location, var)
            self.current_block.append(inst)
        else:
            self.visit(node.lvalue)
            var = node.lvalue.mem_location

            if node.op == "=":
                inst = ('store_'+str(node.rvalue.uc_type)+"_*", node.rvalue.gen_location, var)
            else:
                inst = (binary_ops[node.op]+"_"+str(node.rvalue.uc_type)+"_*", node.lvalue.gen_location, node.rvalue.gen_location, var)
            self.current_block.append(inst)

    def visit_Break(self, node):
        inst = ("jump", "%"+self.loop_pile[-1])
        self.current_block.append(inst)

    def visit_FuncCall(self, node):
        func_name = node.declarator.name
        if isinstance(node.arguments, ExprList):
            for arg in node.arguments.exprs:
                self.visit(arg)
                inst = ("param_"+str(arg.uc_type), arg.gen_location)
                self.current_block.append(inst)
        else:
            self.visit(node.arguments)
            inst = ('param_'+str(node.arguments.uc_type), node.arguments.gen_location)
            self.current_block.append(inst)

        res = self.new_temp()
        inst = ('call_'+str(node.declarator.uc_type), "@"+func_name, res)
        self.current_block.append(inst)
        node.gen_location = res

    def visit_Assert(self, node):
        # assert block
        cond_name = self.new_name("assert")
        cond_block = ConditionBlock(cond_name)

        # assert fail
        fail_name = self.new_name("assert.fail")
        fail_block = BasicBlock(fail_name)

        # end (assert deu certo)
        end_name = self.new_name("assert.end")
        end_block = BasicBlock(end_name)

        # setup condicao
        cond_block.predecessors.append(self.current_block)
        self.current_block.branch = cond_block
        cond_block.taken = end_block
        cond_block.fall_through = fail_block

        self.current_block.next_block = cond_block
        self.current_block = cond_block
        self.visit(node.expr)
        inst = ("cbranch", node.expr.gen_location, "%"+end_name, "%"+fail_name)
        self.current_block.append(inst)

        # setup do assert
        fail_block.predecessors.append(cond_block)

        msg = self.new_text("str")
        inst = ("global_string", msg, "assertion_fail on"+str(node.expr.coord).split('@')[1])
        self.text.append(inst)
        self.current_block.next_block = fail_block
        self.current_block = fail_block
        inst = (fail_name+":",)
        self.current_block.append(inst)
        inst = ("print_string", msg)
        self.current_block.append(inst)
        inst = ("jump", "%exit")
        self.current_block.append(inst)

        # setup do end
        fail_block.predecessors.append(fail_block)
        fail_block.predecessors.append(cond_block)

        self.current_block.next_block = end_block
        self.current_block = end_block
        inst = (end_name+":",)
        self.current_block.append(inst)

    def visit_Read(self, node):
        pass
        # TODO para cada nome visitar, carregar se necessário e gerar instrução de read

    def visit_Return(self, node):
        if node.expr is not None:
            self.visit(node.expr)
            typename = str(node.expr.uc_type)
            inst = ('store_'+typename, node.expr.gen_location, self.return_register)
            self.current_block.append(inst)

        #inst = ('jump', "%exit")
        
    # Expressões : para cada expressão criar uma nova variável temporária, criar uma instrução para salvar o valor da expressão na variável
    # e salvar o nome da variável temporária onde o valor foi colocado como atributo na AST (chamado de gen_location no código de exemplo)

    def visit_ID(self, node):
        target = self.new_temp()
        source = self._get_origin(node.name)
        inst = ('load_'+str(node.uc_type), source, target)
        self.current_block.append(inst)
        node.gen_location = target

    def visit_Cast(self, node):
        self.visit(node.value)
        tgt = self.new_temp()
        if node.type.name == 'int':
            inst = ("fptosi", node.value.gen_location, tgt)
        else:
            inst = ("sitofp", node.value.gen_location, tgt)
        self.current_block.append(inst)
        node.gen_location = tgt


    def visit_UnaryOp(self, node):
        self.visit(node.expr)
        if node.op not in ["!", "-", "+", "*", "/"]:
            _1 = self.new_temp()
            inst = ("literal_int", 1, _1)
            self.current_block.append(inst)
            name = self._get_origin(node.expr.name)
            if node.op.startswith('p'):
                temp = self.new_temp()
                inst = ('alloc_int', temp)
                self.current_block.append(inst)
                inst = ('store_int', name, temp)
                self.current_block.append(inst)
                if node.op == "p++":
                    inst = ("add_int", node.expr.gen_location, _1, name)
                else:
                    inst = ("sub_int", node.expr.gen_location, _1, name)
                self.current_block.append(inst)
                node.gen_location = temp
            else:
                if node.op == "++":
                    inst = ("add_int", node.expr.gen_location, _1, name)
                else:
                    inst = ("sub_int", node.expr.gen_location, _1, name)
                self.current_block.append(inst)
                node.gen_location = name

        # "-", "+", "*", "/", "!"
        else:
            typename = str(node.expr.uc_type).split('[')[0]
            res = self.new_temp()
            if node.op == "!":
                inst = ("not_"+typename, node.expr.gen_location, res)
                self.current_block.append(inst)
            else:
                _0 = self.new_temp()
                inst = ("literal_"+typename, 0, _0)
                self.current_block.append(inst)
                inst = (binary_ops[node.op]+"_"+typename, _0, node.expr.gen_location, res)
                self.current_block.append(inst)
            node.gen_location = res

    def visit_ExprList(self, node):
        pass
        # não fazer nada?? a exprlist deve ser tratada no escopo que a usa

    def visit_ArrayRef(self, node):
        nm = self._get_name(node)
        name = self._get_origin(nm)
        typename = str(node.uc_type).split('[')[0]

        if not isinstance(node.id, ArrayRef):
            # Caso uni-dimensional
            # visitar a posicao e carregar seu valor para memoria
            self.visit(node.pos)
            index = node.pos.gen_location

            # carregar o valor do array na posicao
            location = self.new_temp()
            inst = ('elem_int', name, index, location)
            self.current_block.append(inst)
            
            value = self.new_temp()
            inst = ("load_"+typename+"_*", location, value)
            self.current_block.append(inst)

        else:
            # caso multi-dimensional
            # lista com as dimensoes do array em ordem
            dims = self.var_dim[nm].split('_')[1:]

            # calcular offset para a posicao desejada
            offset = self.new_temp()
            inst = ("literal_int", 0, offset)
            self.current_block.append(inst)
            produtorio = self.new_temp()
            inst = ("literal_int", 1, produtorio)
            self.current_block.append(inst)

            i = len(dims)-1
            aux = node
            while isinstance(aux, ArrayRef):
                self.visit(aux.pos)
                pos = aux.pos.gen_location
                dim = self.new_temp()
                termo = self.new_temp()
                inst = ("mul_int", pos, produtorio, termo)
                self.current_block.append(inst)
                inst = ("add_int", offset, termo, offset)
                self.current_block.append(inst)
                inst = ("literal_int", int(dims[i]), dim)
                self.current_block.append(inst)
                # produtorio das dimensoes (a instrucao deve ser executada em ordem inversa, por isso a lista diferente)
                inst = ("mul_int", dim, produtorio, produtorio)
                self.current_block.append(inst)

                aux = aux.id
                i -= 1
            
            location = self.new_temp()
            inst = ("elem_"+typename, name, offset, location)
            self.current_block.append(inst)

            value = self.new_temp()
            inst = ("load_"+typename+"_*", location, value)
            self.current_block.append(inst)

        node.gen_location = value
        node.mem_location = location


    def visit_InitList(self, node):
        node.code = []

        for item in node.decls:
            if isinstance(item, InitList):
                self.visit(item)
                node.code.append(item.code)
            else:
                value = item.value
                if item.type == 'int':
                    value = int(value)
                elif item.type == 'float':
                    value = float(value)
                # TODO mudar os tipos de string para os tipos corretos

                node.code.append(value)

        # Diz qual o tamanho do item mais interno no caso de InitLists aninhadas (necessario para ArrayDecl sem o tam da ultima dimensao)
        if isinstance(node.decls[0], InitList):
            node.last_dim_size = node.decls[0].last_dim_size
        else:
            node.last_dim_size = node.size


if __name__ == "__main__":

    # create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_file",
        help="Path to file to be used to generate uCIR. By default, this script only runs the interpreter on the uCIR. \
              Use the other options for printing the uCIR, generating the CFG or for the debug mode.",
        type=str,
    )
    parser.add_argument(
        "--ir",
        help="Print uCIR generated from input_file.",
        action="store_true",
    )
    parser.add_argument(
        "--cfg", help="Show the cfg of the input_file.", action="store_true"
    )
    parser.add_argument(
        "--debug", help="Run interpreter in debug mode.", action="store_true"
    )
    args = parser.parse_args()

    print_ir = args.ir
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

    gen = CodeGenerator(create_cfg)
    gen.visit(ast)
    gencode = gen.code

    if print_ir:
        print("Generated uCIR: --------")
        gen.show()
        print("------------------------\n")

    vm = Interpreter(interpreter_debug)
    vm.run(gencode)
