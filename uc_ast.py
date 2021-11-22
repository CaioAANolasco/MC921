import sys


def represent_node(obj, indent):
    def _repr(obj, indent, printed_set):
        """
        Get the representation of an object, with dedicated pprint-like format for lists.
        """
        if isinstance(obj, list):
            indent += 1
            sep = ",\n" + (" " * indent)
            final_sep = ",\n" + (" " * (indent - 1))
            return (
                "["
                + (sep.join((_repr(e, indent, printed_set) for e in obj)))
                + final_sep
                + "]"
            )
        elif isinstance(obj, Node):
            if obj in printed_set:
                return ""
            else:
                printed_set.add(obj)
            result = obj.__class__.__name__ + "("
            indent += len(obj.__class__.__name__) + 1
            attrs = []
            for name in obj.__slots__[:-1]:
                if name == "bind":
                    continue
                value = getattr(obj, name)
                value_str = _repr(value, indent + len(name) + 1, printed_set)
                attrs.append(name + "=" + value_str)
            sep = ",\n" + (" " * indent)
            final_sep = ",\n" + (" " * (indent - 1))
            result += sep.join(attrs)
            result += ")"
            return result
        elif isinstance(obj, str):
            return obj
        else:
            return ""

    # avoid infinite recursion with printed_set
    printed_set = set()
    return _repr(obj, indent, printed_set)


class Node:
    """Abstract base class for AST nodes."""

    __slots__ = "coord"
    attr_names = ()

    def __init__(self, coord=None):
        self.coord = coord

    def __repr__(self):
        """Generates a python representation of the current node"""
        return represent_node(self, 0)

    def children(self):
        """A sequence of all children that are Nodes"""
        pass

    def show(
        self,
        buf=sys.stdout,
        offset=0,
        attrnames=False,
        nodenames=False,
        showcoord=False,
        _my_node_name=None,
    ):
        """Pretty print the Node and all its attributes and children (recursively) to a buffer.
        buf:
            Open IO buffer into which the Node is printed.
        offset:
            Initial offset (amount of leading spaces)
        attrnames:
            True if you want to see the attribute names in name=value pairs. False to only see the values.
        nodenames:
            True if you want to see the actual node names within their parents.
        showcoord:
            Do you want the coordinates of each Node to be displayed.
        """
        lead = " " * offset
        if nodenames and _my_node_name is not None:
            buf.write(lead + self.__class__.__name__ + " <" + _my_node_name + ">: ")
            inner_offset = len(self.__class__.__name__ + " <" + _my_node_name + ">: ")
        else:
            buf.write(lead + self.__class__.__name__ + ":")
            inner_offset = len(self.__class__.__name__ + ":")

        if self.attr_names:
            if attrnames:
                nvlist = [
                    (n, represent_node(getattr(self, n), offset+inner_offset+1+len(n)+1))
                    for n in self.attr_names
                    if getattr(self, n) is not None
                ]
                attrstr = ", ".join("%s=%s" % nv for nv in nvlist)
            else:
                vlist = [getattr(self, n) for n in self.attr_names]
                attrstr = ", ".join(
                    represent_node(v, offset + inner_offset + 1) for v in vlist
                )
            buf.write(" " + attrstr)

        if showcoord:
            if self.coord and self.coord.line != 0:
                buf.write(" %s" % self.coord)
        buf.write("\n")

        for (child_name, child) in self.children():
            child.show(buf, offset + 4, attrnames, nodenames, showcoord, child_name)


class Program(Node):
    __slots__ = ("gdecls", "coord", "text")

    def __init__(self, gdecls, coord=None):
        self.gdecls = gdecls
        self.coord = coord

    def children(self):
        nodelist = []
        for i, child in enumerate(self.gdecls or []):
            nodelist.append(("gdecls[%d]" % i, child))
        return tuple(nodelist)

class GlobalDecl(Node):
    __slots__ = ("declaration", "coord")

    def __init__(self, declaration, coord=None):
        self.declaration = declaration
        self.coord = coord

    def children(self):
        nodelist = []
        for i, child in enumerate(self.declaration or []):
            nodelist.append(("declaration[%d]" % i, child))
        return tuple(nodelist)

class BinaryOp(Node):
    __slots__ = ("op", "left", "right", "coord", "uc_type", "gen_location")

    def __init__(self, op, left, right, coord=None):
        self.op = op
        self.left = left
        self.right = right
        self.coord = coord
        self.uc_type = None
        self.gen_location = None

    def children(self):
        nodelist = []
        if self.left is not None:
            nodelist.append(("left", self.left))
        if self.right is not None:
            nodelist.append(("right", self.right))
        return tuple(nodelist)

    attr_names = ("op", )


class Constant(Node):
    __slots__ = ("type", "value", "uc_type", "coord", "gen_location")

    def __init__(self, type, value, coord=None):
        self.type = type
        self.value = value
        self.coord = coord
        self.uc_type = None
        self.gen_location = None

    def children(self):
        return ()

    attr_names = ("type", "value")

class ID(Node):
    __slots__ = ("name", "coord", "uc_type", "scope", "gen_location")

    def __init__(self, name, coord=None):
        self.name = name
        self.coord = coord
        self.uc_type = None
        self.scope = None
        self.gen_location = None

    def children(self):
        return ()

    attr_names = ("name", )

class ArrayDecl(Node):
    __slots__ = ("expr", "type", "coord", "uc_type", "init", "dim")

    def __init__(self, expr, type=None, coord=None):
        self.expr = expr
        self.type = type
        self.coord = coord
        self.uc_type = None
        self.init = None
        self.dim = None

    def children(self):
        nodelist = []
        if self.type is not None:
            nodelist.append(("type", self.type))
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)

class ArrayRef(Node):
    __slots__ = ("id", "pos", "coord", "uc_type", "gen_location", "mem_location")

    def __init__(self, id, pos, coord=None):
        self.id = id
        self.pos = pos
        self.coord = coord
        self.uc_type = None
        self.gen_location = None
        self.mem_location = None

    def children(self):
        nodelist = []
        if self.id is not None:
            nodelist.append(("id", self.id))
        if self.pos is not None:
            nodelist.append(("pos", self.pos))
        return tuple(nodelist)

class Assert(Node):
    __slots__ = ("expr", "coord")

    def __init__(self, expr, coord=None):
        self.expr = expr
        self.coord = coord

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)

class Assignment(Node):
    __slots__ = ("op", "lvalue", "rvalue", "coord", "uc_type")

    def __init__(self, op, lvalue, rvalue, coord=None):
        self.op = op
        self.lvalue = lvalue
        self.rvalue = rvalue
        self.coord = coord
        self.uc_type = None

    def children(self):
        nodelist = []
        if self.lvalue is not None:
            nodelist.append(("lvalue", self.lvalue))
        if self.rvalue is not None:
            nodelist.append(("rside", self.rvalue))
        
        return tuple(nodelist)

    attr_names = ("op", )

class Break(Node):
    __slots__ = ("coord", "inside_loop")

    def __init__(self, coord=None):
        self.coord = coord
        self.inside_loop = False

    def children(self):
        return ()

class Cast(Node):
    __slots__ = ("type", "value", "coord", "uc_type", "gen_location")

    def __init__(self, type, value, coord=None):
        self.type = type
        self.value = value
        self.coord = coord
        self.uc_type = None
        self.gen_location = None

    def children(self):
        nodelist = []
        if self.type is not None:
            nodelist.append(("type", self.type))
        if self.value is not None:
            nodelist.append(("value", self.value))
        return tuple(nodelist)

class Compound(Node):
    __slots__ = ("decls", "statmts", "coord")

    def __init__(self, decls, statmts ,coord=None):
        self.decls = decls
        self.statmts = statmts
        self.coord = coord

    def children(self):
        nodelist = []
        for i, child in enumerate(self.decls or []):
           if child is not None and not isinstance(child, list):
               nodelist.append(("decls[%d]" % i, child))
        for i, child in enumerate(self.statmts or []):
            if child is not None and not isinstance(child, list):
                nodelist.append(("statmts[%d]" % i, child))

        return tuple(nodelist)

class Decl(Node):
    __slots__ = ("name", "type", "init", "coord", "uc_type")

    def __init__(self, name, type, init, coord=None):
        self.name = name
        self.type = type
        self.init = init
        self.coord = coord
        self.uc_type = None

    def children(self):
        nodelist = []
        if self.type is not None:
            nodelist.append(("type", self.type))
        if isinstance(self.init, Node):
            nodelist.append(("init", self.init))
        elif isinstance(self.init, list):
            for i, child in enumerate(self.init or []):
                nodelist.append(("init[%d]" % i, child))
        return tuple(nodelist)

    attr_names = ("name", )

class DeclList(Node):
    __slots__ = ("decls", "coord")

    def __init__(self, decls, coord=None):
        self.decls = decls
        self.coord = coord

    def children(self):
        nodelist = []
        for i, child in enumerate(self.decls or []):
            nodelist.append(("decl[%d]" % i, child))
        return tuple(nodelist)

class EmptyStatement(Node):
    __slots__ = ("coord")

    def __init__(self, coord=None):
        self.coord = coord

    def children(self):
        return ()

class ExprList(Node):
    __slots__ = ("exprs", "coord", "expr_types")

    def __init__(self, exprs, coord=None):
        self.exprs = exprs
        self.coord = coord
        self.expr_types = []

    def children(self):
        nodelist = []
        if isinstance(self.exprs, list):
            for i, child in enumerate(self.exprs or []):
                nodelist.append(("expr[%d]" % i, child))
        elif self.exprs is not None:
            nodelist.append(("exprs", self.exprs))
        return tuple(nodelist)

class FuncCall(Node):
    __slots__ = ("declarator", "arguments", "coord", "uc_type", "gen_location")

    def __init__(self, declarator, arguments, coord=None):
        self.declarator = declarator
        self.arguments = arguments
        self.coord = coord
        self.uc_type = None
        self.gen_location = None

    def children(self):
        nodelist = []
        if self.declarator is not None:
            nodelist.append(("declarator", self.declarator))
        if self.arguments is not None:
            nodelist.append(("arguments", self.arguments))
        return tuple(nodelist)

class FuncDecl(Node):
    __slots__ = ("declarator", "param_list", "type", "coord", "uc_type", "code", "text", "init")

    def __init__(self, declarator, param_list, type=None, coord=None):
        self.declarator = declarator
        self.param_list = param_list
        self.type = type
        self.coord = coord
        self.uc_type = None
        self.code = None
        self.text = None
        self.init = None

    def children(self):
        nodelist = []
        if self.param_list is not None and not isinstance(self.param_list, list):
            nodelist.append(("param_list", self.param_list))
        if self.type is not None:
            nodelist.append(("type", self.type))
        return tuple(nodelist)

class FuncDef(Node):
    __slots__ = ("type", "name", "declaration", "compound_statement", "coord", "uc_type", "hasReturn", "cfg")

    def __init__(self, t, name, declaration, compound_statement, coord=None):
        self.type = t
        self.name = name
        self.declaration = declaration
        self.compound_statement = compound_statement
        self.coord = coord
        self.uc_type = None
        self.hasReturn = False
        self.cfg = None

    def children(self):
        nodelist = []
        if isinstance(self.type, Node):
            nodelist.append(("type", self.type))
        if isinstance(self.name, Node):
            nodelist.append(("name", self.name))
        if isinstance(self.compound_statement, Node):
            nodelist.append(("compound_statement", self.compound_statement))
        for i, child in enumerate(self.declaration or []):
            nodelist.append(("declaration[%d]" % i, child))

        return tuple(nodelist)

class If(Node):
    __slots__ = ("expr", "ifstat", "elsestat", "coord")

    def __init__(self, expr, ifstat, elsestat=None, coord=None):
        self.expr = expr
        self.ifstat = ifstat
        self.elsestat = elsestat
        self.coord = coord

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        if self.ifstat is not None:
            nodelist.append(("ifstat", self.ifstat))
        if self.elsestat is not None:
            nodelist.append(("elsestat", self.elsestat))
        return tuple(nodelist)

class InitList(Node):
    __slots__ = ("decls", "coord", "uc_type", "size", "code", "last_dim_size")

    def __init__(self, decls, coord=None):
        self.decls = decls
        self.coord = coord
        self.uc_type = None
        self.size = len(decls)
        self.code = None
        self.last_dim_size = None

    def children(self):
        nodelist = []
        for i, child in enumerate(self.decls or []):
           nodelist.append(("decl[%d]" % i, child))
        return tuple(nodelist)

class ParamList(Node):
    __slots__ = ("params", "coord", "param_types", "code", "text")

    def __init__(self, params, coord=None):
        self.params = params
        self.coord = coord
        self.param_types = {}
        self.code = None
        self.text = None

    def children(self):
        nodelist = []
        for i, child in enumerate(self.params or []):
            nodelist.append(("params[%d]" % i, child))
        return tuple(nodelist)

class PtrDecl(Node):
    __slots__ = ("pointer", "decl", "coord")

    def __init__(self, pointer, decl, coord=None):
        self.pointer = pointer
        self.decl = decl
        self.coord = coord

    def children(self):
        return ()

class VarDecl(Node):
    __slots__ = ("type", "declname", "coord", "uc_type", "init", "dim")

    def __init__(self, type, declname, coord=None):
        self.type = type
        self.declname = declname
        self.coord = coord
        self.uc_type = None
        self.init = None
        self.dim = ""

    def children(self):
        nodelist = []
        if self.type is not None:
            nodelist.append(("type", self.type))
        return tuple(nodelist)

class Type(Node):
    __slots__ = ("name", "coord")

    def __init__(self, name, coord=None):
        self.name = name
        self.coord = coord

    def children(self):
        return ()

    attr_names = ("name", )

class UnaryOp(Node):
    __slots__ = ("op", "expr", "coord", "uc_type", "gen_location")

    def __init__(self, op, expr, coord=None):
        self.op = op
        self.expr = expr
        self.coord = coord
        self.uc_type = None
        self.gen_location = None

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)

    attr_names = ("op", )

class While(Node):
    __slots__ = ("expr", "stat", "coord")

    def __init__(self, expr, stat, coord=None):
        self.expr = expr
        self.stat = stat
        self.coord = coord

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        if self.stat is not None:
            nodelist.append(("stat", self.stat))
        return tuple(nodelist)

class For(Node):
    __slots__ = ("t1", "t2", "t3", "stat", "coord")

    def __init__(self, t1, t2, t3, stat, coord=None):
        self.t1 = t1
        self.t2 = t2
        self.t3 = t3
        self.stat = stat
        self.coord = coord

    def children(self):
        nodelist = []
        if not isinstance(self.t1, list):
            nodelist.append(("t1", self.t1))
        else:
            for i, child in enumerate(self.t1 or []):
                nodelist.append(("t1[%d]" % i, child))
        if self.t2 is not None:
            nodelist.append(("t2", self.t2))
        if self.t3 is not None:
            nodelist.append(("t3", self.t3))
        if self.stat is not None:
            nodelist.append(("stat", self.stat))
        return tuple(nodelist)

class Read(Node):
    __slots__ = ("expr", "coord")

    def __init__(self, expr, coord=None):
        self.expr = expr
        self.coord = coord

    def children(self):
        nodelist = []
        if isinstance(self.expr, list):
            for i, child in enumerate(self.expr or []):
                nodelist.append(("expr[%d]" % i, child))
        elif self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)

class Return(Node):
    __slots__ = ("expr", "coord", "function_name", "uc_type")

    def __init__(self, expr, coord=None):
        self.expr = expr
        self.coord = coord
        self.function_name = None
        self.uc_type = None

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)

class Print(Node):
    __slots__ = ("expr", "coord")

    def __init__(self, expr, coord=None):
        self.expr = expr
        self.coord = coord

    def children(self):
        nodelist = []
        if self.expr is not None:
            nodelist.append(("expr", self.expr))
        return tuple(nodelist)
