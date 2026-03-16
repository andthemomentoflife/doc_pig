import ast


def Stmtyp(t1, t2) -> bool:
    if t1 == t2:
        return True
    for pair in simpair:
        if (t1 in pair) and (t2 in pair):
            return True
    return False


stmt = [
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Return,
    ast.Delete,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Raise,
    ast.Try,
    ast.Assert,
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Expr,
    ast.Pass,
    ast.Break,
    ast.Continue,
    # ast.comprehension
]

single_stmt = [
    ast.Return,
    ast.Delete,
    ast.Assign,
    ast.AugAssign,
    ast.AnnAssign,
    ast.Raise,
    ast.Assert,
    ast.Global,
    ast.Nonlocal,
    ast.Expr,
]

expr = [
    ast.BoolOp,
    ast.NamedExpr,
    ast.BinOp,
    ast.UnaryOp,
    ast.Lambda,
    ast.IfExp,
    ast.Dict,
    ast.Set,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Await,
    ast.Yield,
    ast.YieldFrom,
    ast.Compare,
    ast.Call,
    ast.FormattedValue,
    ast.JoinedStr,
    ast.Constant,
    ast.Attribute,
    ast.Subscript,
    ast.Starred,
    ast.Name,
    ast.List,
    ast.Tuple,
    ast.Slice,
    ast.comprehension,
    ast.withitem,  # 새로 추가
    ast.keyword,  # 새로 추가
    ast.ExceptHandler,
]

ctx = [ast.Load, ast.Store, ast.Del]

"""
Arbitrary Defined Similar Stmts in Python -> needs to be validated somehow....

                Compound statements 
                FunctionDef(identifier name, arguments args,
                                    stmt* body, expr* decorator_list, expr? returns,
                                    string? type_comment, type_param* type_params)
                | AsyncFunctionDef(identifier name, arguments args,
                                            stmt* body, expr* decorator_list, expr? returns,
                                            string? type_comment, type_param* type_params)
                | ClassDef(identifier name,
                            expr* bases,
                            keyword* keywords,
                            stmt* body,
                            expr* decorator_list,
                            type_param* type_params)

                Compound statements - Iterative Stmts
                | For(expr target, expr iter, stmt* body, stmt* orelse, string? type_comment)
                | AsyncFor(expr target, expr iter, stmt* body, stmt* orelse, string? type_comment)
                | While(expr test, stmt* body, stmt* orelse)


                Compound and Single - Variable Assign
                        | Assign(expr* targets, expr value, string? type_comment)
                        | AugAssign(expr target, operator op, expr value)
                        -- 'simple' indicates that we annotate simple name without parens
                        | AnnAssign(expr target, expr annotation, expr? value, int simple)
                        | With(withitem* items, stmt* body, string? type_comment)
                        | AsyncWith(withitem* items, stmt* body, string? type_comment)

"""

simpair1 = [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]
simpair2 = [ast.For, ast.AsyncFor, ast.While, ast.comprehension]
simpair3 = [ast.Assign, ast.AugAssign, ast.AnnAssign, ast.With, ast.AsyncWith, ast.Expr]
simpair4 = [ast.Import, ast.ImportFrom]
simpair5 = [ast.Global, ast.Nonlocal]
simpair6 = [ast.Raise, ast.Assert]
simpair7 = [ast.Expr, ast.Call]
simpair8 = [ast.BoolOp, ast.UnaryOp]


simpair = [
    simpair1,
    simpair2,
    simpair3,
    simpair4,
    simpair5,
    simpair6,
    simpair7,
    simpair8,
]
