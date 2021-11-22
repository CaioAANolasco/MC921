import argparse
import pathlib
import sys
from ply.yacc import yacc
from uc.uc_ast import (
    ID,
    ArrayDecl,
    ArrayRef,
    Assert,
    Assignment,
    BinaryOp,
    Break,
    Cast,
    Compound,
    Constant,
    Decl,
    DeclList,
    EmptyStatement,
    ExprList,
    For,
    FuncCall,
    FuncDecl,
    FuncDef,
    GlobalDecl,
    If,
    InitList,
    ParamList,
    Print,
    Program,
    PtrDecl,
    Read,
    Return,
    Type,
    UnaryOp,
    VarDecl,
    While,
    represent_node,
)
from uc.uc_lexer import UCLexer


class Coord:
    """Coordinates of a syntactic element. Consists of:
    - Line number
    - (optional) column number, for the Lexer
    """

    __slots__ = ("line", "column")

    def __init__(self, line, column=None):
        self.line = line
        self.column = column

    def __str__(self):
        if self.line and self.column is not None:
            coord_str = "@ %s:%s" % (self.line, self.column)
        elif self.line:
            coord_str = "@ %s" % (self.line)
        else:
            coord_str = ""
        return coord_str


class UCParser:
    def __init__(self, debug=True):
        """Create a new uCParser."""
        self.uclex = UCLexer(self._lexer_error)
        self.uclex.build()
        self.tokens = self.uclex.tokens

        self.ucparser = yacc(module=self, start="program", debug=debug)
        # Keeps track of the last token given to yacc (the lookahead token)
        self._last_yielded_token = None

    def parse(self, text, debuglevel=0):
        self.uclex.reset_lineno()
        self._last_yielded_token = None
        return self.ucparser.parse(input=text, lexer=self.uclex, debug=debuglevel)

    def _lexer_error(self, msg, line, column):
        # use stdout to match with the output in the .out test files
        print("LexerError: %s at %d:%d" % (msg, line, column), file=sys.stdout)
        sys.exit(1)

    def _parser_error(self, msg, coord=None):
        # use stdout to match with the output in the .out test files
        if coord is None:
            print("ParserError: %s" % (msg), file=sys.stdout)
        else:
            print("ParserError: %s %s" % (msg, coord), file=sys.stdout)
        sys.exit(1)

    def _token_coord(self, p, token_idx):
        last_cr = p.lexer.lexer.lexdata.rfind("\n", 0, p.lexpos(token_idx))
        if last_cr < 0:
            last_cr = -1
        column = p.lexpos(token_idx) - (last_cr)
        return Coord(p.lineno(token_idx), column)

    def _build_declarations(self, spec, decls):
        """Builds a list of declarations all sharing the given specifiers."""
        declarations = []

        for decl in decls:
            assert decl["decl"] is not None
            declaration = Decl(
                name=None,
                type=decl["decl"],
                init=decl.get("init"),
                coord=decl["decl"].coord,
            )

            fixed_decl = self._fix_decl_name_type(declaration, spec)
            declarations.append(fixed_decl)

        return declarations

    def _fix_decl_name_type(self, decl, typename):
        """Fixes a declaration. Modifies decl."""
        # Reach the underlying basic type
        type = decl
        while not isinstance(type, VarDecl):
            type = type.type

        decl.name = type.declname
        if not typename:
            # Functions default to returning int
            if not isinstance(decl.type, FuncDecl):
                self._parser_error("Missing type in declaration", decl.coord)
            type.type = Type("int", coord=decl.coord)
        else:
            type.type = Type(typename.name, coord=typename.coord)

        return decl

    def _type_modify_decl(self, decl, modifier):
        """Tacks a type modifier on a declarator, and returns
        the modified declarator.
        Note: the declarator and modifier may be modified
        """
        modifier_head = modifier
        modifier_tail = modifier

        # The modifier may be a nested list. Reach its tail.
        while modifier_tail.type:
            modifier_tail = modifier_tail.type

        # If the decl is a basic type, just tack the modifier onto it
        if isinstance(decl, VarDecl):
            modifier_tail.type = decl
            return modifier
        else:
            # Otherwise, the decl is a list of modifiers. Reach
            # its tail and splice the modifier onto the tail,
            # pointing to the underlying basic type.
            decl_tail = decl

            while not isinstance(decl_tail.type, VarDecl):
                decl_tail = decl_tail.type

            modifier_tail.type = decl_tail.type
            decl_tail.type = modifier_head
            return decl

    precedence = (
        ('left', 'IF'),
        ('left', 'ELSE'),
        ('left', 'EQUALS', 'PLUSEQUAL', 'MINUSEQUAL', 'TIMESEQUAL', 'DIVEQUAL', 'MODEQUAL'),
        ('left', 'OR'),
        ('left', 'AND'),
        ('nonassoc', 'LT', 'GT', 'LE', 'GE'),
        ('left', 'EQ', 'NE'),
        ('left', 'PLUS', 'MINUS'),
        ('left', 'TIMES', 'DIVIDE', 'MOD'),
        ('left', 'NOT', 'PLUSPLUS', 'MINUSMINUS'),
    )

    def p_program(self, p):
        """program  : global_declaration_list
        """
        p[0] = Program(p[1])
        #p[0].show(showcoord=True)
        

    def p_global_declaration_list(self, p):
        """ global_declaration_list : global_declaration
        | global_declaration_list global_declaration
        """
        p[0] = [p[1]] if len(p) == 2 else p[1] + [p[2]]


    def p_global_declaration(self, p):
        """ global_declaration : function_definition
        """
        p[0] = p[1]
    def p_global_declaration2(self, p):
        """global_declaration : declaration
        """
        p[0] = GlobalDecl(p[1])
    def p_global_declaration3(self, p):
        """ global_declaration : ucomment
        | unquote 
        """
        pass

    def p_function_definition(self, p):
        """ function_definition : declarator m_declaration compound_statement
        | type_specifier declarator m_declaration compound_statement
        """
        if len(p) == 4:
            void = Type("void")
            decl = Decl(None, p[1], None)
            decl = self._fix_decl_name_type(decl, void)
            p[0] = FuncDef(void, decl, p[2], p[3])
        else:
            decl = Decl(None, p[2], None)
            decl = self._fix_decl_name_type(decl, p[1])
            p[0] = FuncDef(p[1], decl, p[3], p[4])


    def p_type_specifier(self, p):
        """ type_specifier : VOID
        | CHAR
        | INT
        | FLOAT
         """
        if p[1] == "void":
            p[0] = Type("void", self._token_coord(p, 1))
        elif p[1] == "char":
            p[0] = Type("char", self._token_coord(p, 1))
        elif p[1] == "int":
            p[0] = Type("int", self._token_coord(p, 1))
        else:
            p[0] = Type("float", self._token_coord(p, 1))


    def p_declarator(self, p):
        """ declarator : direct_declarator
        | pointer direct_declarator
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = PtrDecl(p[1], p[2])


    def p_pointer(self, p):
        """ pointer : TIMES zo_pointer """
        p[0] = p[1]


    def p_direct_declarator(self, p):
        """ direct_declarator : ID
        | LPAREN declarator RPAREN
        | direct_declarator LPAREN m_identifier RPAREN
        | direct_declarator LPAREN parameter_list RPAREN
        | direct_declarator LBRACKET constant_expression RBRACKET
        | direct_declarator LBRACKET RBRACKET
        """
        if len(p) == 2 and p[1] is not None:
            p[0] = VarDecl(None, ID(p[1], self._token_coord(p, 1)))
        elif p[1] == "(":
            p[0] = p[2]
        elif p[2] == "(":
            if isinstance(p[3], list):
                p[3] = ParamList(p[3], p[3][0].coord)
            p[0] = FuncDecl(None, p[3], p[1])
        elif len(p) == 5:
            if isinstance(p[1], ArrayDecl):
                decl = ArrayDecl(p[3], None)
                p[0] = self._type_modify_decl(p[1], decl)
            else:
                p[0] = ArrayDecl(p[3], p[1])
        else:
            if isinstance(p[1], ArrayDecl):
                decl = ArrayDecl(None, None)
                p[0] = self._type_modify_decl(p[1], decl)
            else:
                p[0] = ArrayDecl(None, p[1])


    def p_m_identifier(self, p):
        """ m_identifier : ID
        | m_identifier COMMA ID
        | empty
        """
        if len(p) == 2 and p[1] is not None:
            p[0] = [ID(p[1], self._token_coord(p, 1))]
        elif len(p) == 4 and p[3] is not None:
            p[0] = p[1] + [ID(p[3], self._token_coord(p, 3))]
        else:
            p[0] = None


    def p_constant_expression(self, p):
        """ constant_expression : binary_expression"""
        p[0] = p[1]


    def p_binary_expression(self, p):
        """ binary_expression : cast_expression
        | binary_expression TIMES binary_expression
        | binary_expression DIVIDE binary_expression
        | binary_expression MOD binary_expression
        | binary_expression PLUS binary_expression
        | binary_expression MINUS binary_expression
        | binary_expression LT binary_expression
        | binary_expression LE binary_expression
        | binary_expression GT binary_expression
        | binary_expression GE binary_expression
        | binary_expression EQ binary_expression
        | binary_expression NE binary_expression
        | binary_expression AND binary_expression
        | binary_expression OR binary_expression
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = BinaryOp(p[2], p[1], p[3], p[1].coord)


    def p_cast_expression(self, p):
        """ cast_expression : unary_expression
        | LPAREN type_specifier RPAREN cast_expression
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = Cast(p[2], p[4], self._token_coord(p, 1))


    def p_unary_expression(self, p):
        """ unary_expression : postfix_expression
        | PLUSPLUS unary_expression
        | MINUSMINUS unary_expression
        | unary_operator cast_expression
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = UnaryOp(p[1], p[2], p[2].coord)


    def p_postfix_expression(self, p):
        """ postfix_expression : primary_expression
        | postfix_expression LBRACKET expression RBRACKET
        | postfix_expression LPAREN expression RPAREN
        | postfix_expression LPAREN RPAREN
        | postfix_expression PLUSPLUS
        | postfix_expression MINUSMINUS
        """
        if len(p) == 2:
            p[0] = p[1]

        elif len(p) == 5 and p[2] == "(":
            if not isinstance(p[3], ExprList):
                if isinstance(p[3], list) and len(p[3]) > 1:
                    p[3] = ExprList(p[3], p[3][0].coord)
                elif isinstance(p[3], list):
                    p[3] = p[3][0]
            p[0] = FuncCall(p[1], p[3], p[1].coord)

        elif len(p) == 4 and p[2] == "(":
            p[0] = FuncCall(p[1], None, p[1].coord)

        elif len(p) == 5:
            p[0] = ArrayRef(p[1], p[3], p[1].coord)

        # elif len(p) == 4:
        #     p[0] = ArrayRef(p[1], None, p[1].coord)

        else:
            p[0] = UnaryOp("p"+p[2], p[1], coord=p[1].coord)


    def p_primary_expression(self, p):
        """ primary_expression : constant
        | LPAREN expression RPAREN
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = p[2]
    def p_primary_expression2(self, p):
        """ primary_expression : ID """
        p[0] = ID(p[1], self._token_coord(p, 1))
    def p_primary_expression3(self, p):
        """ primary_expression : STRING_LITERAL """
        p[0] = Constant("string", p[1], self._token_coord(p, 1))


    def p_constant(self, p):
        """ constant : CHAR_CONST """
        p[0] = Constant("char", p[1], self._token_coord(p, 1))
    def p_constant2(self, p):
        """ constant : INT_CONST """
        p[0] = Constant("int", p[1], self._token_coord(p, 1))
    def p_constant3(self, p):
        """ constant : FLOAT_CONST """
        p[0] = Constant("float", p[1], self._token_coord(p, 1))


    def p_expression(self, p):
        """ expression : assigment_expression
        | expression COMMA assigment_expression
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            if not isinstance(p[1], ExprList):
                p[1] = ExprList([p[1]], p[1].coord)
                
            p[1].exprs.append(p[3])
            p[0] = p[1]


    def p_assigment_expression(self, p):
        """ assigment_expression : binary_expression
        | unary_expression assigment_operator assigment_expression """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = Assignment(p[2], p[1], p[3], p[1].coord)


    def p_assigment_operator(self, p):
        """ assigment_operator : EQUALS
        | TIMESEQUAL
        | DIVEQUAL
        | MODEQUAL
        | PLUSEQUAL
        | MINUSEQUAL
        """
        p[0] = p[1]


    def p_unary_operator(self, p):
        """ unary_operator : UAND
        | TIMES
        | PLUS
        | MINUS
        | NOT
        """
        p[0] = p[1]


    def p_parameter_list(self, p):
        """ parameter_list : parameter_declaration
        | parameter_list COMMA parameter_declaration """
        if len(p) == 2:
            p[0] = [p[1]]
        else:
            p[0] = p[1] + [p[3]]


    def p_parameter_declaration(self, p):
        """ parameter_declaration : type_specifier declarator """
        p[2] = Decl(None, p[2], None)
        p[0] = self._fix_decl_name_type(p[2], p[1])


    def p_declaration(self, p):
        """ declaration : type_specifier init_declarator_list SEMI
        | type_specifier SEMI
        """
        if len(p) == 4:
            p[0] = self._build_declarations(p[1], p[2])
        else:
            print("invalid declaration?")


    def p_init_declarator_list(self, p):
        """ init_declarator_list : init_declarator
        | init_declarator_list COMMA init_declarator
        """
        if len(p) == 2:
            p[0] = [p[1]]
        else:
            p[0] = p[1] + [p[3]]


    def p_init_declarator(self, p):
        """ init_declarator : declarator
        | declarator EQUALS initializer
        """
        if len(p) == 2:
            p[0] = {"decl": p[1], "init": None}
        else:
            p[0] = {"decl": p[1], "init": p[3]}


    def p_initializer(self, p):
        """ initializer : assigment_expression
        | LBRACE RBRACE
        | LBRACE initializer_list RBRACE
        | LBRACE initializer_list COMMA RBRACE
        """
        if len(p) == 2:
            p[0] = p[1]
        elif len(p) == 3:
            p[0] = InitList(None, self._token_coord(p, 1))
        else:
            p[0] = InitList(p[2], self._token_coord(p, 1))


    def p_initializer_list(self, p):
        """ initializer_list : initializer
        | initializer_list COMMA initializer
        """
        if len(p) == 2:
            p[0] = [p[1]]
        else:
            p[0] = p[1] + [p[3]]


    def p_compund_statement(self, p):
        """ compound_statement : LBRACE m_declaration m_statement RBRACE"""
        p[0] = Compound(p[2], p[3], self._token_coord(p, 1))


    def p_statement(self, p):
        """ statement : expression_statement
        | compound_statement
        | selection_statement
        | iteration_statement
        | jump_statement
        | assert_statement
        | print_statement
        | read_statement
        """
        p[0] = p[1]


    def p_expression_statement(self, p):
        """ expression_statement : zo_expression SEMI"""
        p[0] = p[1]


    def p_selection_statement(self, p):
        """ selection_statement : IF LPAREN expression RPAREN statement ELSE statement
        | IF LPAREN expression RPAREN statement
        """
        if len(p) == 6:
            p[0] = If(p[3], p[5], coord=self._token_coord(p, 1))
        else:
            p[0] = If(p[3], p[5], p[7], coord=self._token_coord(p, 1))


    def p_iteration_statement(self, p):
        """ iteration_statement : WHILE LPAREN expression RPAREN statement
        | FOR LPAREN expression_statement expression_statement zo_expression RPAREN statement
        """
        if len(p) == 6:
            p[0] = While(p[3], p[5], self._token_coord(p, 1))
        else:
            p[0] = For(p[3], p[4], p[5], p[7], self._token_coord(p, 1))
    def p_iteration_statement2(self, p):
        """ iteration_statement : FOR LPAREN declaration expression_statement zo_expression RPAREN statement """
        p[0] = For(DeclList(p[3], self._token_coord(p, 1)), p[4], p[5], p[7], self._token_coord(p, 1))


    def p_jump_statement(self, p):
        """ jump_statement : BREAK SEMI """
        p[0] = Break(self._token_coord(p, 1))
    def p_jump_statement2(self, p):
        """ jump_statement : RETURN expression_statement """
        p[0] = Return(p[2], self._token_coord(p, 1))

    def p_assert_statement(self, p):
        """ assert_statement : ASSERT expression SEMI """
        p[0] = Assert(p[2], self._token_coord(p, 1))


    def p_print_statement(self, p):
        """ print_statement : PRINT LPAREN expression RPAREN SEMI 
        | PRINT LPAREN RPAREN SEMI
        """
        if len(p) == 6:
            p[0] = Print(p[3], self._token_coord(p, 1))
        else:
            p[0] = Print(None, self._token_coord(p, 1))


    def p_read_statement(self, p):
        """ read_statement : READ LPAREN expression RPAREN SEMI """
        p[0] = Read(p[3], self._token_coord(p, 1))


    def p_empty(self, p):
        """ empty : 
        """
        pass

    def p_zo_expression(self, p):
        """ zo_expression : expression
        | empty
        """
        p[0] = p[1]


    def p_zo_pointer(self, p):
        """ zo_pointer : pointer
        | empty
        """
        p[0] = p[1]


    def p_m_declaration(self, p):
        """ m_declaration : declaration
        | m_declaration declaration
        | empty
        """
        # declaration já é list
        if len(p) == 2:
            p[0] = p[1]
        elif len(p) == 3:
            p[0] = p[1] + p[2]
        

    def p_m_statement(self, p):
        """ m_statement : statement
        | m_statement statement
        | empty
        """
        if len(p) == 2:
            p[0] = [p[1]]
        else:
            p[0] = p[1] + [p[2]]


    def p_error(self, p):
        if p:
            self._parser_error(
                "Before %s" % p.value, Coord(p.lineno, self.uclex.find_tok_column(p))
            )
        else:
            self._parser_error("At the end of input (%s)" % self.uclex.filename)


if __name__ == "__main__":

    # create argument parser
    parser = argparse.ArgumentParser()
    parser.add_argument("input_file", help="Path to file to be parsed", type=str)
    args = parser.parse_args()

    # get input path
    input_file = args.input_file
    input_path = pathlib.Path(input_file)

    # check if file exists
    if not input_path.exists():
        print("ERROR: Input", input_path, "not found", file=sys.stderr)
        sys.exit(1)

    def print_error(msg, x, y):
        print("Lexical error: %s at %d:%d" % (msg, x, y), file=sys.stderr)

    # set error function
    p = UCParser()
    # open file and print tokens
    with open(input_path) as f:
        p.parse(f.read())
