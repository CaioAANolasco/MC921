import argparse
import pathlib
import sys
from uc.uc_ast import (ID, Break, ExprList, ArrayRef, FuncDecl, ParamList, 
    Node, Constant, InitList, FuncCall, Return, Decl)
from uc.uc_parser import UCParser
from uc.uc_type import CharType, FloatType, IntType, VoidType, BoolType, StringType, ArrayType

class SymbolTable(dict):
    """Class representing a symbol table. It should provide functionality
    for adding and looking up nodes associated with identifiers.
    """

    def __init__(self):
        super().__init__()
        self.scope = []
        self.args = {}

    def add(self, name, value, args=None, scp=-1):
        self[name] = (value, self.get(name, None))
        self.args[name] = (args, self.args.get(name, None))
        self.scope[scp].append(name)

    def lookup(self, name):
        value = self.get(name, None)
        if value is not None:
            return value[0]
        else:
            return None
    
    def lookup_args(self, name):
        args = self.args.get(name, None)
        if args is not None:
            return args[0]
        else:
            return None

    def remove(self, name):
        # Remoção do nome da tabela de simbolos
        value = self.get(name, None)
        if value is not None:
            self[name] = value[1]

        # Remoção dos argumentos da função
        args = self.args.get(name, None)
        if args is not None:
            self.args[name] = args[1]

    def beginscope(self):
        self.scope.append([])

    def endscope(self):
        for name in self.scope[-1]:
            self.remove(name)
        self.scope.pop(-1)

    # -2 significa que a variável está declarada no escopo atual
    # -1 que está declarada em algum escopo externo
    # 0 que não está declarada
    def declared(self, name):
        if name in self.scope[-1] and self.get(name, None) is not None:
            return -2
        if self.get(name, None) is not None:
            return -1
        return 0


class NodeVisitor:
    """A base NodeVisitor class for visiting uc_ast nodes.
    Subclass it and define your own visit_XXX methods, where
    XXX is the class name you want to visit with these
    methods.
    """

    _method_cache = None

    def visit(self, node):
        """Visit a node."""

        if self._method_cache is None:
            self._method_cache = {}

        visitor = self._method_cache.get(node.__class__.__name__, None)
        if visitor is None:
            method = "visit_" + node.__class__.__name__
            visitor = getattr(self, method, self.generic_visit)
            self._method_cache[node.__class__.__name__] = visitor

        return visitor(node)

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a
        node. Implements preorder visiting of the node.
        """
        if not isinstance(node, Node):
            return
        for _, child in node.children():
            self.visit(child)


class Visitor(NodeVisitor):
    """
    Program visitor class. This class uses the visitor pattern. You need to define methods
    of the form visit_NodeName() for each kind of AST node that you want to process.
    """

    def __init__(self):
        # Initialize the symbol table
        self.symtab = SymbolTable()
        self.typemap = {
            "int": IntType,
            "float": FloatType,
            "char": CharType,
            "bool": BoolType,
            "string": StringType,
            "void": VoidType,
        }
        # TODO: Complete...

    def _assert_semantic(self, condition, msg_code, coord, name="", ltype="", rtype=""):
        """Check condition, if false print selected error message and exit"""
        error_msgs = {
            1: f"{name} is not defined",
            2: f"{ltype} must be of type(int)",
            3: "Expression must be of type(bool)",
            4: f"Cannot assign {rtype} to {ltype}",
            5: f"Assignment operator {name} is not supported by {ltype}",
            6: f"Binary operator {name} does not have matching LHS/RHS types",
            7: f"Binary operator {name} is not supported by {ltype}",
            8: "Break statement must be inside a loop",
            9: "Array dimension mismatch",
            10: f"Size mismatch on {name} initialization",
            11: f"{name} initialization type mismatch",
            12: f"{name} initialization must be a single element",
            13: "Lists have different sizes",
            14: "List & variable have different sizes",
            15: f"conditional expression is {ltype}, not type(bool)",
            16: f"{name} is not a function",
            17: f"no. arguments to call {name} function mismatch",
            18: f"Type mismatch with parameter {name}",
            19: "The condition expression must be of type(bool)",
            20: "Expression must be a constant",
            21: "Expression is not of basic type",
            22: f"{name} does not reference a variable of basic type",
            23: f"\n{name}\nIs not a variable",
            24: f"Return of {ltype} is incompatible with {rtype} function definition",
            25: f"Name {name} is already defined in this scope",
            26: f"Unary operator {name} is not supported",
            27: "Undefined error",
        }
        if not condition:
            msg = error_msgs.get(msg_code)
            print("SemanticError: %s %s" % (msg, coord), file=sys.stdout)
            sys.exit(1)

    def _find_break(self, node):
        if isinstance(node, Break):
            node.inside_loop = True
        else:
            for _, child in node.children():
                self._find_break(child)

    def _find_return(self, node, f, f_name):
        if isinstance(node, Return):
            node.function_name = f_name
            node.uc_type = node.expr.uc_type
            self._assert_semantic(str(node.uc_type) == str(f.uc_type), 24, node.coord, ltype="type("+str(node.uc_type)+")", rtype="type("+str(f.uc_type)+")")
            f.hasReturn = True
        else:
            for _, child in node.children():
                self._find_return(child, f, f_name)

    # checa se a declaração do array é válida
    def _check_array(self, node, init):
        array_type = node.uc_type
        if init is not None:
            #checa se os arrays são do mesmo tipo e mesmo número de dimensões
            if isinstance(init, InitList):
                self._check_dim(init, node)

            #checa se os arrays são do mesmo tamanho
            if array_type.size is not None and isinstance(init, InitList):
                self._assert_semantic(str(array_type) == str(init.uc_type), 14, node.name.coord)

            if array_type.size is not None:
                self._assert_semantic(str(array_type) == str(init.uc_type), 10, node.name.coord, name=node.name.name)

            # coloca tamanho do init list no array para facilitar a geracao do IR (Projeto parte 5)
            if array_type.size is None:
                array_type.size = init.uc_type.size
        else:
            while hasattr(array_type, "type"):
                self._assert_semantic(array_type.size is not None, 9, node.name.coord)
                array_type = array_type.type

    def _check_dim(self, init_list, node):
        prevChild = None
        is_list = False
        is_constant = False
        for child in init_list.decls:
            if (is_list and isinstance(child, Constant)) or (is_constant and isinstance(child, InitList)):
                pass
                #TODO lista inválida
            if is_list:
                self._assert_semantic(prevChild.size == child.size, 13, node.name.coord)
            if isinstance(child, Constant):
                is_constant = True
                prevChild = child
            elif isinstance(child, InitList):
                is_list = True
                prevChild = child
            

    def visit_Program(self, node):
        self.symtab.beginscope()

        # Visit all of the global declarations
        for _decl in node.gdecls:
            self.visit(_decl)

        self.symtab.endscope()

    def visit_BinaryOp(self, node):
        # Visit the left and right expression
        self.visit(node.left)
        ltype = node.left.uc_type
        self.visit(node.right)
        rtype = node.right.uc_type

        self._assert_semantic(ltype.__str__() == rtype.__str__(), 6, node.coord, name=node.op)
        
        if node.op in ltype.binary_ops:
            node.uc_type = ltype
        elif node.op in ltype.rel_ops:
            node.uc_type = self.typemap["bool"]
        else:
            self._assert_semantic(False, 7, node.coord, name=node.op, ltype="type("+str(ltype)+")")

    def visit_Assignment(self, node):
        # visit right side
        self.visit(node.rvalue)
        rtype = node.rvalue.uc_type
        # visit left side (must be a location)
        _var = node.lvalue
        self.visit(_var)
        if isinstance(_var, ID):
            self._assert_semantic(_var.scope is not None, 1, node.coord, name=_var.name)
        ltype = node.lvalue.uc_type
        # Check that assignment is allowed
        self._assert_semantic(ltype.__str__() == rtype.__str__(), 4, node.coord, ltype="type("+str(ltype)+")", rtype="type("+str(rtype)+")")
        # Check that assign_ops is supported by the type
        self._assert_semantic(
            node.op in ltype.assign_ops, 5, node.coord, name=node.op, ltype="type("+str(ltype)+")"
        )
        node.uc_type = self.typemap["void"]

    def visit_VarDecl(self, node):
        type = node.type.name
        
        node.uc_type = self.typemap[type]

    def visit_Decl(self, node):
        name = node.name.name
        
        #escopo termina no FuncDef
        if isinstance(node.type, FuncDecl):
            self.symtab.beginscope()

        self.visit(node.type)
        node.uc_type = node.type.uc_type

        self._assert_semantic(self.symtab.declared(name) != -2, 25, node.name.coord, name=name)

        if isinstance(node.type, FuncDecl):
            if node.type.param_list is not None:
                self.symtab.add(name, node.uc_type, node.type.param_list.param_types, scp=-2)
            else:
                self.symtab.add(name, node.uc_type, {}, scp=-2)
        else:
            self.symtab.add(name, node.uc_type)
        
        if node.init is not None:
            self.visit(node.init)

            if not isinstance(node.uc_type, ArrayType) and isinstance(node.init, InitList):
                self._assert_semantic(False, 12, node.name.coord, name=name)
            if not isinstance(node.uc_type, ArrayType):
                self._assert_semantic(node.uc_type.__str__() == node.init.uc_type.__str__(), 11, coord=node.name.coord, name=name)

        if isinstance(node.uc_type, ArrayType):
            self._check_array(node, node.init)


    def visit_ID(self, node):
        self._assert_semantic(self.symtab.declared(node.name) < 0, 1, node.coord, name=node.name)
        node.scope = True
        node.uc_type = self.symtab.lookup(node.name)
        

    def visit_Constant(self, node):
        if node.type != "string":
            node.uc_type = self.typemap[node.type]
        else:
            node.uc_type = ArrayType(self.typemap["char"], len(node.value))

    def visit_FuncDef(self, node):
        node.name.uc_type = self.typemap[node.type.name]
        node.uc_type = node.name.uc_type
        self.visit(node.name)

        # nome dos argumentos e conteúdo da função estão em um escopo interno

        if isinstance(node.declaration, list):
            for item in node.declaration:
                self.visit(item)

        self.visit(node.compound_statement)

        if str(node.uc_type) != "void":
            self._find_return(node.compound_statement, node, node.name.name.name)
            self._assert_semantic(node.hasReturn, 24, node.compound_statement.coord, name="", ltype="type(void)", rtype="type("+str(node.uc_type)+")")
        

        self.symtab.endscope()

    def visit_FuncDecl(self, node):
        if node.declarator is not None:
            self.visit(node.declarator)
        self.visit(node.type)
        node.uc_type = node.type.uc_type

        if node.param_list is not None:
            self.visit(node.param_list)

    def visit_ParamList(self, node):
        for child in node.params:
            if isinstance(child, Decl):
                self.visit(child)
                node.param_types[child.name] = child.uc_type
        
    def visit_FuncCall(self, node):
        self.visit(node.declarator)
        self._assert_semantic(self.symtab.lookup_args(node.declarator.name) is not None, 16, node.coord, node.declarator.name)

        node.uc_type = node.declarator.uc_type

        if node.arguments is not None:
            self.visit(node.arguments)
            def_args = self.symtab.lookup_args(node.declarator.name)

            if isinstance(node.arguments, ExprList):
                call_args = node.arguments.expr_types

                self._assert_semantic(len(call_args) == len(def_args), 17, node.coord, node.declarator.name)
                
                for i, def_arg, in enumerate(def_args or []):
                    self._assert_semantic(def_args[def_arg].__str__() == call_args[i][0].__str__(), 18, call_args[i][1].coord, def_arg.name)
            else:
                pass
                # TODO unico argumento, pegar UC_type da Decl

            #TODO verificar quantidade e tipo dos argumentos


    def visit_ArrayDecl(self, node):
        self.visit(node.type)
        if node.expr is not None:
            node.uc_type = ArrayType(node.type.uc_type, node.expr.value)
        else:
            node.uc_type = ArrayType(node.type.uc_type, None)

    def visit_ArrayRef(self, node):
        self.visit(node.id)
        self.visit(node.pos)
        self._assert_semantic(str(node.pos.uc_type) == "int", 2, node.pos.coord, name="", ltype="type("+str(node.pos.uc_type)+")")
        
        node.uc_type = node.id.uc_type.type

    def visit_InitList(self, node):
        for child in node.decls:
            self._assert_semantic(isinstance(child, Constant) or isinstance(child, InitList), 20, child.coord)
            self.visit(child)

        node.uc_type = ArrayType(node.decls[0].uc_type, len(node.decls))

    def visit_For(self, node):
        self.symtab.beginscope()

        self._find_break(node)

        for _, child in node.children():
            self.visit(child)
        
        self.symtab.endscope()

    def visit_While(self, node):
        self.symtab.beginscope()

        self._find_break(node)

        self.visit(node.expr)
        self._assert_semantic(node.expr.uc_type.__str__() == "bool", 15, node.coord, ltype="type("+str(node.expr.uc_type)+")")
        self.visit(node.stat)

        self.symtab.endscope()

    def visit_Break(self, node):
        self._assert_semantic(node.inside_loop, 8, node.coord)

    def visit_UnaryOp(self, node):
        self.visit(node.expr)
        node.uc_type = node.expr.uc_type

        self._assert_semantic(node.op in node.uc_type.unary_ops, 26, node.coord, node.op)

    def visit_Read(self, node):
        self.visit(node.expr)

        self._assert_semantic(
            isinstance(node.expr, ID) or isinstance(node.expr, ExprList) or isinstance(node.expr, ArrayRef), 
            23, node.expr.coord, node.expr
        )

    def visit_ExprList(self, node):
        for child in node.exprs:
            self.visit(child)
            node.expr_types.append((child.uc_type, child))

    def visit_Print(self, node):
        child = node.expr
        self.visit(child)

        if isinstance(child, ID):
            self._assert_semantic(child.uc_type.__str__() in ("int", "char", "float", "string", "char[]"), 22, child.coord, child.name)
        elif isinstance(child, FuncCall):
            self._assert_semantic(child.declarator.uc_type.__str__() in ("int", "char", "float", "string", "char[]"), 21, child.declarator.coord, child.declarator.name)

        # TODO quando for multiplas expressões
    
    def visit_If(self, node):
        self.symtab.beginscope()

        for _, child in node.children():            
            self.visit(child)

        self._assert_semantic(node.expr.uc_type.__str__() == "bool", 19, node.expr.coord)

        self.symtab.endscope()

    def visit_Assert(self, node):
        self.visit(node.expr)
        self._assert_semantic(str(node.expr.uc_type) == "bool", 3, node.expr.coord)

    def visit_Return(self, node):
        if node.expr is not None:
            self.visit(node.expr)
            node.uc_type = node.expr.uc_type

    def visit_Cast(self, node):
        for _, child in node.children():
            self.visit(child)
        node.uc_type = self.typemap[node.type.name]

    def visit_Compound(self, node):
        self.symtab.beginscope()

        for _, child in node.children():
            self.visit(child)

        self.symtab.endscope()

if __name__ == "__main__":

    # create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_file", help="Path to file to be semantically checked", type=str
    )
    args = parser.parse_args()

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
        ast = p.parse(f.read(), debuglevel=0)
        sema = Visitor()
        sema.visit(ast)
