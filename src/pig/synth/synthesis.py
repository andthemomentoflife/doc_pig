from _ast import (
    AnnAssign,
    Assert,
    Assign,
    AsyncFor,
    AsyncFunctionDef,
    AsyncWith,
    Delete,
    Expr,
    For,
    Global,
    If,
    Nonlocal,
    Raise,
    Return,
    Try,
    While,
    With,
    alias,
)
import ast, sys

from os import path

from typing import Union

if __package__ is None:
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))

try:
    import call, llm_pre
except:
    from synth import call, llm_pre

try:
    from stmt_types import stmt as stmt_type
except:
    from .stmt_types import stmt as stmt_type


from typing import Union

import ast


def return_first_index(var, parent, node, nodeo, noden):
    def check(var, stmt):
        for node in ast.walk(stmt):
            if (
                (isinstance(node, ast.Name))
                and (node.id == var)
                and isinstance(node.ctx, ast.Load)
            ):
                return True

            if (isinstance(node, ast.Attribute)) and (ast.unparse(node) == var):
                return True
        return False

    if hasattr(parent, "body") and (nodeo in parent.body or noden in parent.body):
        target = parent.body

    elif hasattr(parent, "orelse") and (
        nodeo in parent.orelse or noden in parent.orelse
    ):
        target = parent.orelse

    elif hasattr(parent, "finalbody") and (
        nodeo in parent.finalbody or noden in parent.finalbody
    ):
        target = parent.finalbody

    else:
        target = None

    if target is not None:
        for stmt in target:
            if check(var, stmt):
                index = target.index(stmt)
                target.insert(index, node)
                break


def with_sur(var, noden: Union[ast.AsyncWith, ast.With], parent):
    def check(var, stmt):
        for node in ast.walk(stmt):
            if (
                (isinstance(node, ast.Name))
                and (node.id == var)
                and isinstance(node.ctx, ast.Load)
            ):
                return True
        return False

    def simple_transplant(noden: Union[ast.AsyncWith, ast.With]):
        if isinstance(noden, ast.AsyncWith):
            node = ast.Await(
                value=ast.Assign(
                    targets=noden.items[0].optional_vars,
                    value=noden.items[0].context_expr,
                )
            )
        else:
            node = ast.Assign(
                targets=noden.items[0].optional_vars, value=noden.items[0].context_expr
            )
        return node

    if hasattr(parent, "body"):
        target = parent.body

    elif hasattr(parent, "orelse"):
        target = parent.orelse

    elif hasattr(parent, "finalbody"):
        target = parent.finalbody

    else:
        target = None

    if target is not None:
        # Find a statement which uses the variable
        for stmt in target:
            if check(var, stmt):
                index = target.index(stmt)
                break

        # Add the nodeo to the body of noden
        noden.body = [target[index]]

        # Remove the nodeo from the target
        target[index] = noden

        return noden

    else:
        print("Error: parento is None")
        # Just change the value with context_expr[0]
        return simple_transplant(noden)


def assign_to_with(
    nodeo: ast.Assign,
    noden: Union[ast.With, ast.AsyncWith],
    parento: dict,
):

    def check(var, stmt):
        for node in ast.walk(stmt):
            if (
                (isinstance(node, ast.Name))
                and (node.id == var)
                and isinstance(node.ctx, ast.Load)
            ):
                return True
        return False

    def simple_transplant(nodeo, noden):
        if isinstance(noden, ast.AsyncWith):
            nodeo.value = ast.Await(value=nodeo.value)
        else:
            nodeo.value = noden.items[0].context_expr
        return nodeo

    """Getting Assign Node and Change it to AsyncWith"""

    # First, figure out the target variable
    if (len(nodeo.targets) == 1) and isinstance(nodeo.targets[0], ast.Name):
        target_var = nodeo.targets[0].id

    else:
        print("Error: nodeo.targets[0] is not ast.Name", nodeo.targets)
        return simple_transplant(nodeo, noden)

    # Second, figure out the sentence using target_var
    target_var_used_stmts = []
    parent_of_nodeo = call.FindSSParent(parento, nodeo)

    if parent_of_nodeo is not None:
        if hasattr(parent_of_nodeo, "body") and nodeo in parent_of_nodeo.body:
            target = parent_of_nodeo.body

        elif hasattr(parent_of_nodeo, "orelse") and nodeo in parent_of_nodeo.orelse:
            target = parent_of_nodeo.orelse

        elif (
            hasattr(parent_of_nodeo, "finalbody") and nodeo in parent_of_nodeo.finalbody
        ):
            target = parent_of_nodeo.finalbody

        else:
            print("Error: parento is None")

        for stmt in target:
            if check(target_var, stmt):
                target_var_used_stmts.append(stmt)

        # Third, remove the target_var_used_stmts from the original nodeo
        start_index = target.index(nodeo) + 1
        end_index = target.index(target_var_used_stmts[-1])
        target_var_used_stmts = target[start_index : end_index + 1]

        # Last, Add the target_var_used_stmts to the body of noden
        noden.body = target[start_index : end_index + 1]

        for stmt in target_var_used_stmts:
            if stmt in target:
                target.remove(stmt)

        # Change optional_vars
        noden.optional_vars = nodeo.targets[0]

        return noden

    else:
        print("Error: parento is None")
        # Just change the value with context_expr[0]
        return simple_transplant(nodeo, noden)


def stmt_to_dec(
    key,
    val: Union[ast.FunctionDef, ast.AsyncFunctionDef],
    h,
    ParentO: dict,
    funcdefs: set,
):
    """Merge decorator lists from a new function node into the matching function in ``h``.

    If the new function name ``val.name`` already exists in ``funcdefs``,
    its decorator list is appended to the matching node found in ``h``.
    Otherwise, the enclosing function or class of ``key`` in the old code
    is located via :func:`call.FindFCParent` and its decorator list is
    updated instead.

    :param key: The old API call node used to locate the enclosing
        function or class when ``val.name`` is not in ``funcdefs``.
    :type key: ast.AST
    :param val: The new function node whose decorator list is to be merged.
    :type val: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    :param h: The current working AST, walked to find the target function.
    :type h: ast.AST
    :param ParentO: The parent mapping of the old code as produced by
        :func:`call.ParentAst`.
    :type ParentO: dict
    :param funcdefs: The set of function names already defined in the
        working AST.
    :type funcdefs: set
    :return: The modified working AST with the decorator list updated.
    :rtype: ast.AST
    """

    new_func_name = val.name

    if new_func_name in funcdefs:
        # Find that function add decorator into it
        for node in ast.walk(h):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == new_func_name
            ):
                if node.decorator_list is None:
                    node.decorator_list = val.decorator_list
                else:
                    node.decorator_list += val.decorator_list

    else:
        # Find the function
        FParent = call.FindFCParent(ParentO, key)
        if FParent is not None:
            # Find the function add decorator into it
            if FParent.decorator_list is None:
                FParent.decorator_list = val.decorator_list
            else:
                FParent.decorator_list += val.decorator_list

    return h


# Due to With, AsyncWith, the target stmts should be deleted
class TrimRoot(ast.NodeTransformer):
    """Remove a specific set of statement nodes from the AST.

    Walks the AST and returns ``None`` for any node found in ``targets``,
    effectively deleting it. :class:`ast.With` and :class:`ast.AsyncWith`
    nodes that match ``exception`` are preserved regardless of whether they
    appear in ``targets``.

    Intended for cleaning up ``With``/``AsyncWith`` target statements that
    have been absorbed into a new context-manager node.

    :param targets: The list of statement nodes to remove.
    :type targets: list[ast.stmt]
    :param exception: A single node that must never be removed, even if it
        appears in ``targets`` (typically the new ``With``/``AsyncWith``
        node that absorbed the targets).
    :type exception: ast.stmt
    """

    def __init__(self, targets: list[ast.stmt], exception):
        self.targets = targets
        self.exception = exception

    def visit_Return(self, node: Return):
        if node in self.targets:
            return None
        return node

    def visit_Delete(self, node: Delete):
        if node in self.targets:
            return None
        return node

    def visit_Assign(self, node: Assign):
        if node in self.targets:
            return None
        return node

    def visit_AugAssign(self, node: ast.AugAssign):
        if node in self.targets:
            return None
        return node

    def visit_AnnAssign(self, node: AnnAssign):
        if node in self.targets:
            return None
        return node

    def visit_For(self, node: For):
        if node in self.targets:
            return None
        return self.generic_visit(node)

    def visit_AsyncFor(self, node: AsyncFor):
        if node in self.targets:
            return None
        return self.generic_visit(node)

    def visit_While(self, node: While):
        if node in self.targets:
            return None
        return self.generic_visit(node)

    def visit_If(self, node: If):
        if node in self.targets:
            return None
        return self.generic_visit(node)

    def visit_With(self, node: With):
        if node in self.targets and node != self.exception:
            return None
        if node == self.exception:
            return node

        return self.generic_visit(node)

    def visit_AsyncWith(self, node: AsyncWith):
        if node in self.targets and node != self.exception:
            return None
        if node == self.exception:
            return node

        return self.generic_visit(node)

    def visit_Match(self, node: ast.Match):
        if node in self.targets:
            return None
        return node

    def visit_Raise(self, node: Raise):
        if node in self.targets:
            return None
        return node

    def visit_Try(self, node: Try):
        if node in self.targets:
            return None
        return self.generic_visit(node)

    def visit_Assert(self, node: Assert):
        if node in self.targets:
            return None
        return node

    def visit_Global(self, node: Global):
        if node in self.targets:
            return None
        return node

    def visit_Nonlocal(self, node: Nonlocal):
        if node in self.targets:
            return None
        return node

    def visit_Expr(self, node: Expr):
        if node in self.targets:
            return None
        return node


class FindSurFCs(ast.NodeVisitor):
    def __init__(self, nv: str):
        self.nv = nv
        self.result = None

        # 내부 클래스 함수일때도 있는데 일단은 무시

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name == self.nv:
            self.result = node

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        if node.name == self.nv:
            self.result = node

    def visit_ClassDef(self, node: ast.ClassDef):
        if node.name == self.nv:
            self.result = node


# Deleting Import Statements | Input: Library Name
class ImportDeleter(ast.NodeTransformer):
    """Remove all import statements that reference a given library.

    Walks the AST and strips any :class:`ast.Import` or
    :class:`ast.ImportFrom` node whose module or alias name contains
    ``libo``. A special case handles ``'ruamel.yaml'`` which uses a dotted
    top-level name.

    :param libo: The library name to remove from import statements.
    :type libo: str
    """

    def __init__(self, libo: str):
        self.libo = libo

    def visit_Import(self, node: ast.Import):
        for name in node.names:
            if self.libo in (name.name.split(".")) or (
                self.libo == name.name and self.libo == "ruamel.yaml"
            ):
                return None
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module == None:
            return node

        if self.libo in (node.module.split(".")):
            return None

        for name in node.names:
            if self.libo in (name.name.split(".")):
                return None

        return node


def Vars(Assigned: dict, Used: dict):
    Unused = dict()
    UnAssigned = dict()

    for key, val in Assigned.items():
        if key in Used.keys():
            Unused[key] = val - Used[key]
            UnAssigned[key] = Used[key] - val
        else:
            Unused[key] = val
            UnAssigned[key] = set()

    return (Unused, UnAssigned)


# Extract all variable names according to the depth of stmt
class VarExtractor(ast.NodeVisitor):
    """Collect all variable names referenced within an AST, organised by scope.

    Walks the AST and records every :class:`ast.Name` identifier into a
    per-scope dict keyed by the enclosing function or class name
    (``'module'`` for top-level code). Import names are collected
    separately in ``self.imports``.

    :param name: The initial scope name. Defaults to ``'module'``.
    :type name: str
    :param check: If ``True``, ``self.<attr>`` assignments are tracked
        as separate qualified names (e.g. ``'self.foo'``).
    :type check: bool

    :ivar vars: Mapping from scope name to the set of variable names
        referenced in that scope.
    :vartype vars: dict[str, set[str]]
    :ivar imports: Set of all imported names and aliases.
    :vartype imports: set[str]
    """

    def __init__(self, name="module", check=False):
        self.vars: dict[str : set[str]] = dict()
        self.vars[name] = set()
        self.imports = set()
        self.name = name
        self.callattr = False
        self.exception = dict()
        self.check = check  # If true, self.output and output are different variable

    def visit_Name(self, node: ast.Name):
        if self.callattr == False and node.id != "self":
            try:
                self.vars[self.name].add(node.id)
            except:
                self.vars[self.name] = {node.id}

    def visit_comprehension(self, node: ast.comprehension):
        self.callattr = False
        self.visit(node.target)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        tmp = self.name
        self.name = node.name  # function name

        if self.name in self.vars.keys():
            pass
        else:
            self.vars[self.name] = set()

        self.visit(node.args)

        for stmt in node.body:
            self.visit(stmt)

        self.name = tmp

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        tmp = self.name
        self.name = node.name

        if self.name in self.vars.keys():
            pass
        else:
            self.vars[self.name] = set()

        self.visit(node.args)

        for stmt in node.body:
            self.visit(stmt)

        self.name = tmp

    def visit_ClassDef(self, node: ast.ClassDef):
        tmp = self.name
        self.name = node.name

        if self.name in self.vars.keys():
            pass
        else:
            self.vars[self.name] = set()

        for stmt in node.body:
            self.visit(stmt)
        self.name = tmp

    def visit_If(self, node: ast.If):
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_For(self, node: For):
        for stmt in node.body:
            self.visit(stmt)

    def visit_Assign(self, node: ast.Assign):
        tlist = []

        tmp1 = call.NameExtractor(check=True, check1=True)
        tmp1.visit(node.value)
        vlist = tmp1.list

        for target in node.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and self.check
            ):
                try:
                    self.vars[self.name].add("self." + target.attr)
                except:
                    self.vars[self.name] = {"self." + target.attr}

            else:
                tmp2 = call.NameExtractor(check=True, check1=True)
                tmp2.visit(target)
                tlist += tmp2.list

        if (
            len(set(tlist) & set(vlist)) != 0
            and len((set(tlist) & set(vlist)) & self.vars[self.name]) < 1
        ):
            try:
                self.exception[node] = self.exception[node] | set(tlist) & set(vlist)
            except:
                self.exception[node] = set(tlist) & set(vlist)

        else:
            for target in node.targets:
                self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self.visit(node.target)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name)
            if alias.asname != None:
                self.imports.add(alias.asname)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module != None:
            self.imports.add(node.module)
        for alias in node.names:
            self.imports.add(alias.name)
            if alias.asname != None:
                self.imports.add(alias.asname)

    def visit_Call(self, node: ast.Call):
        self.callattr = True

        for arg in node.args:
            self.visit(arg)

        self.callattr = False

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.name:
            try:
                self.vars[self.name].add(node.name)
            except:
                self.vars[self.name] = {node.name}

    def visit_Attribute(self, node: ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and self.check
            and isinstance(node.ctx, ast.Store)
        ):
            try:
                self.vars[self.name].add("self." + node.attr)
            except:
                self.vars[self.name] = {"self." + node.attr}

        else:
            pass

    def visit_arguments(self, node: ast.arguments):
        for posonlyarg in node.posonlyargs:
            self.vars[self.name].add(posonlyarg.arg)

        for arg in node.args:
            self.vars[self.name].add(arg.arg)

        for kwonlyarg in node.kwonlyargs:
            self.vars[self.name].add(kwonlyarg.arg)

        if node.vararg != None:
            self.vars[self.name].add(node.vararg.arg)


# func -> async, func -> async | Modify Decorator
class AsyncFD(ast.NodeTransformer):
    def __init__(self, NCF: ast.FunctionDef, check0: bool, check1: bool) -> ast.AST:
        self.NCF = NCF
        self.check0 = check0  # func -> async boolean
        self.check1 = check1  # Modify the function decorator list

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if (node == self.NCF) and (self.check0):
            node = ast.AsyncFunctionDef(
                name=node.name,
                args=node.args,
                body=node.body,
                decorator_list=node.decorator_list,
            )
            return node

        if (node == self.NCF) and (self.check1):
            node.decorator_list = self.NCF.decorator_list
            return node

        return node

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        # if (node == self.NCF) and (self.check0):
        #     node = ast.FunctionDef(
        #         name=node.name,
        #         args=node.args,
        #         body=node.body,
        #         decorator_list=node.decorator_list,
        #     )
        #     return node

        if (node == self.NCF) and (self.check1):
            node.decorator_list = self.NCF.decorator_list
            return node

        return node


# parent stmt의 종류가 같거나 비슷한 경우, llm code 그대로 집어넣기
class SynthSame(ast.NodeTransformer):
    def __init__(
        self,
        OCNP: ast.stmt,
        NCNP: ast.stmt,
        history: set,
        ParentO,
        HAS_CB=False,
        HAS_DEC=False,
    ) -> ast.AST:
        self.NCNP = NCNP
        self.OCNP = OCNP
        self.check = False
        self.HAS_CB = HAS_CB
        self.history = (
            history  # changed new nodes (only stmts) -> 바꾼거 또 바꾸는거 막게
        )
        self.ParentO = ParentO
        self.HAS_DEC = HAS_DEC
        self.HAS_W = False
        self.W_stmts = list()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        if (
            self.HAS_CB
            and isinstance(self.NCNP, ast.ClassDef)
            and node.name == self.NCNP.name
        ):  # Change the class-base
            self.history.add(self.NCNP)
            node.bases = self.NCNP.bases
            return node

        if (
            (self.OCNP == node)
            and node not in self.history
            and isinstance(self.NCNP, ast.ClassDef)
        ):
            self.history.add(self.NCNP)
            node.decorator_list = self.NCNP.decorator_list
            return node  # Class Base 바꾸기

        else:
            return self.generic_visit(node)

    def visit_Return(self, node: Return):
        if (self.OCNP == node) and node not in self.history:
            if isinstance(self.NCNP, ast.Return):
                # Return -> Return
                node.value = self.NCNP.value
                return ast.copy_location(self.NCNP, node)

            elif isinstance(self.NCNP, ast.Assign):
                # Assign -> Return
                node.value = self.NCNP.value
                self.history.add(node)
                return node

            elif isinstance(self.NCNP, ast.Expr):
                # Expr -> Return
                node.value = self.NCNP.value
                self.history.add(node)
                return node

            else:
                node.value = self.NCNP
                self.history.add(node)
                print("Warning: NCNP is not Return, Assign, or Expr", self.NCNP)
                return node

        else:
            return self.generic_visit(node)

    def visit_Delete(self, node: Delete):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Assign(self, node: Assign):
        if (self.OCNP == node) and node not in self.history:
            # Modify
            if isinstance(self.NCNP, (ast.AsyncWith, ast.With)):
                self.NCNP = assign_to_with(node, self.NCNP, self.ParentO)

            elif isinstance(self.NCNP, ast.Call):
                self.NCNP = ast.Assign(targets=node.targets, value=self.NCNP)

            elif isinstance(self.NCNP, ast.Return):
                self.NCNP = ast.Assign(targets=node.targets, value=self.NCNP.value)

            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        else:
            return self.generic_visit(node)

    def visit_AnnAssign(self, node: AnnAssign):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_For(self, node: For):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_AsyncFor(self, node: AsyncFor):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_While(self, node: While):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_If(self, node: If):
        if isinstance(self.NCNP, ast.If):
            self.NCNP.body = node.body
            self.NCNP.orelse = node.orelse
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_With(self, node: With):
        # AsyncWith -> With
        if (
            (self.OCNP == node)
            and node not in self.history
            and isinstance(self.NCNP, (ast.With, ast.AsyncWith))
        ):
            self.history.add(node)
            node.items = self.NCNP.items
            return node
        else:
            return self.generic_visit(node)

    def visit_AsyncWith(self, node: AsyncWith):
        if (
            (self.OCNP == node)
            and node not in self.history
            and isinstance(self.NCNP, (ast.With, ast.AsyncWith))
        ):
            self.history.add(node)
            node.items = self.NCNP.items
            return node
        else:
            return self.generic_visit(node)

    def visit_Raise(self, node: Raise):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Try(self, node: Try):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Assert(self, node: Assert):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Global(self, node: Global):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Nonlocal(self, node: Nonlocal):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Expr(self, node: Expr):
        if (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, ast.Expr)
        ):
            self.history.add(self.NCNP)
            return ast.fix_missing_locations(ast.copy_location(self.NCNP, node))

        elif (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, ast.Await)
        ):
            self.NCNP = ast.fix_missing_locations(ast.Expr(value=self.NCNP))
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, ast.Call)
        ):
            self.NCNP = ast.fix_missing_locations(ast.Expr(value=self.NCNP))
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, ast.Assign)
        ):
            # self.NCNP = ast.fix_missing_locations(ast.Expr(value=self.NCNP.value))
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, (ast.With))
        ):
            self.NCNP = ast.fix_missing_locations(
                ast.Expr(value=self.NCNP.items[0].context_expr)
            )
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif (
            (self.OCNP == node)
            and (node not in self.history)
            and isinstance(self.NCNP, ast.Return)
        ):
            self.NCNP = ast.fix_missing_locations(ast.Expr(value=self.NCNP))
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        else:
            # If ... ()
            return self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare):
        if (self.OCNP == node) and node not in self.history:
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        if self.OCNP == node and isinstance(self.NCNP, ast.Call):
            self.check = True
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif self.OCNP == node and isinstance(self.NCNP, ast.Expr):
            self.check = True
            self.history.add(self.NCNP.value)
            return ast.copy_location(self.NCNP.value, node)

        else:
            return self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        if (self.OCNP == node) and isinstance(self.NCNP, ast.Name):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.alias):
            self.check = True
            if self.NCNP.asname != None:
                node.id = self.NCNP.asname
            else:
                node.id = self.NCNP.name

            return node

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Attribute):
            self.check = True
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Tuple):
            # Exception Handler
            self.check = True
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)

        else:
            return self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple):
        if (self.OCNP == node) and self.OCNP not in self.history:
            self.check = True
            self.history.add(self.NCNP)
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        FLE = llm_pre.FindLastExpr(self.ParentO, node, 1)

        if (self.OCNP == node) and isinstance(self.NCNP, ast.Attribute):

            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (
            (self.OCNP == node)
            and isinstance(self.NCNP, ast.Call)
            and isinstance(FLE, ast.Call)
        ):
            self.check = True
            FLE.args = self.NCNP.args
            # keyword not supported
            return ast.copy_location(self.NCNP.func, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Name) and self.HAS_DEC:
            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Call):
            # 임시방편
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Name):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Tuple):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        else:
            return self.generic_visit(node)

    def visit_Subscript(self, node):
        if (self.OCNP == node) and isinstance(self.NCNP, ast.Subscript):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Attribute):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        elif (self.OCNP == node) and isinstance(self.NCNP, ast.Call):
            self.check = True
            return ast.copy_location(self.NCNP, node)

        else:
            return self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if self.OCNP == node:
            self.check = True
            self.NCNP.body = node.body  # body part should be same with the bef node
            return ast.copy_location(self.NCNP, node)
        else:
            return self.generic_visit(node)


# import 문 추가
class SynthImport(ast.NodeTransformer):
    """Prepend a set of new import statements to the module body.

    Visits the :class:`ast.Module` node and inserts all nodes in
    ``NCImports`` at the beginning of ``node.body``.

    :param NCImports: The set of import nodes to prepend.
    :type NCImports: set[Union[ast.Import, ast.Module, ast.ImportFrom]]
    """

    def __init__(
        self, NCImports: set[Union[ast.Import, ast.Module, ast.ImportFrom]]
    ) -> ast.AST:
        self.NCImports = NCImports

    def visit_Module(self, node: ast.Module):
        # try: newbody = [imp.body[0] for imp in self.NCImports] + node.body
        newbody = [imp for imp in self.NCImports] + node.body
        node.body = newbody
        return node


# Assume that most UnAssignedVars can be solved by the Assign stmts
def FindSurNode(
    UnAssignedVar: str,
    root,
    exception,
    coden,
    ParentO,
    ParentN,
    AssignedVarsO,
    AssignedVarsN,
    CENs,
    history,
    mappings,
    libo,
    libn,
    RelationO,
    rooto,
    h,
    apio,
    FuncDefs,
    check=False,
) -> (
    ast.Assign
    | ast.With
    | ast.AsyncWith
    | ast.ClassDef
    | ast.FunctionDef
    | ast.AsyncFunctionDef
    | None
):
    # Simple Case (Just add the line)
    for node in ast.walk(root):
        if isinstance(node, ast.Assign) and node not in exception:
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == UnAssignedVar:
                    return node

                if (
                    isinstance(target, ast.Attribute)
                    and ast.unparse(target) == UnAssignedVar
                ):
                    return node

                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name) and elt.id == UnAssignedVar:
                            return node
                else:
                    pass

        if isinstance(node, ast.With) or isinstance(node, ast.AsyncWith):
            for item in node.items:
                if item.optional_vars != None and UnAssignedVar in ast.unparse(
                    item.optional_vars
                ):
                    return node

        # if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        #     if node.name == UnAssignedVar:
        #         return node

    if check:
        return None  # The surround node should be searched for deeeper node

    # Complicated Case: where it needs the variable is directly used in specific line!
    # 1. First, find the target line
    targeto = None

    for node in ast.walk(rooto):
        if type(node) in stmt_type:
            if isinstance(node, ast.Assign):  # Target 만 보기
                NEC = call.NameExtractor(check=True)
                NEC.visit(node.value)
                if UnAssignedVar in NEC.list:
                    targeto = node
                    break

            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Try)
            ):  # Target 만 보기
                pass

            elif type(node) in [ast.For, ast.AsyncFor]:  # Iter 만 보기
                NEC = call.NameExtractor(check=True)
                NEC.visit(node.iter)
                if UnAssignedVar in NEC.list:
                    targeto = node
                    break

            elif type(node) in [ast.While, ast.If]:  # test 만 보기
                NEC = call.NameExtractor(check=True)
                NEC.visit(node.test)
                if UnAssignedVar in NEC.list:
                    targeto = node
                    break

            elif type(node) in [ast.With, ast.AsyncWith]:  # withitems만 보기
                for item in node.items:
                    NEC = call.NameExtractor(check=True)
                    NEC.visit(item.context_expr)
                    if UnAssignedVar in NEC.list:
                        targeto = node
                        break

            else:
                NEC = call.NameExtractor(check=True)
                NEC.visit(node)
                if UnAssignedVar in NEC.list:
                    targeto = node
                    break

    if targeto == None:
        # raise Exception("This should not happen. No use case in the code for the variable," , UnAssignedVar)
        return None  # 아예 사용 ㄴㄴ 하는 변수도 있을 수 있자나

    # 2. Second, find the direct match from newcode >> 바꿔야됨
    noden, _ = llm_pre.MatchName(
        targeto, coden, ParentO, ParentN, mappings, False, False, libo, libn
    )
    if noden == None:
        return None

    targetn = noden
    MUVC = llm_pre.ModUseVars(mappings, FuncDefs, ParentN)
    targetn = MUVC.visit(targetn)

    # 3 Change it with SynthSame
    if type(targeto) in [ast.For, ast.AsyncFor]:
        targeto = targeto.iter
        targetn = noden.iter

    elif type(targeto) in [ast.While, ast.If]:
        targeto = targeto.test
        targetn = noden.test

    elif type(node) in [ast.With, ast.AsyncWith]:  # withitems만 보기
        # Assume only one withitem
        targeto = targeto.items[0].context_expr
        targetn = noden.items[0].context_expr

    else:
        pass

    SSC = SynthSame(targeto, targetn, history["changes"], ParentO)
    h = SSC.visit(h)

    return (None, h)  # Directly solved


def Surround(
    h,
    nodeo,
    noden,
    target_names: set,
    root: ast.Module,
    gp,
    coden,
    history: dict,
    mappings: dict,
    index: int,
    name: str,
    ParentO: dict,
    ParentN: dict,
    apio: str,
    FuncDefs: set,
    exceptions: set,
    libo: str,
    rootb_str,
    roota_str,
    rooto,
    roota,
):

    SurNodes = set()
    stack = set()
    remains = set()  # Variables that cannot be solved by the current code
    exception = set()  # 왜

    while True:
        if len(target_names) == 0:
            break

        nv = target_names.pop()

        if llm_pre.check_two_sim(roota, h, nv, noden, rootb_str, SurNodes):
            continue

        tmp_node = noden
        tmp_pnode = call.FindSSParent(ParentN, tmp_node)
        SurNode = None

        # loop until it finds the variable
        while True:
            if tmp_pnode == None:
                SurNode: ast.Assign | ast.AsyncWith | ast.With | ast.Class = (
                    FindSurNode(
                        nv,
                        coden,
                        exception,
                        coden,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        mappings,
                        libo,
                        None,
                        None,
                        None,
                        root,
                        apio,
                        FuncDefs,
                        check=True,
                    )
                )  # None should be turened to root,,,
                break

            SurNode: ast.Assign | ast.AsyncWith | ast.With | ast.Class = FindSurNode(
                nv,
                tmp_pnode,
                exception,
                coden,
                None,
                None,
                None,
                None,
                None,
                None,
                mappings,
                libo,
                None,
                None,
                None,
                root,
                apio,
                FuncDefs,
                check=True,
            )  # None should be turene dto root,,,

            if SurNode != None:
                # new valueast.unparse(SurNode), "SurNode")
                # target_names.add(nv) >> 이거 없앴는데 내일 와서 side effect 생기는지 확인
                break

            else:
                tmp_node = tmp_pnode

            tmp_pnode = call.FindRealParent(ParentN, tmp_node, depth=2)

        # SurNode can be additional declaration
        if SurNode == None:
            FSFC = FindSurFCs(nv)
            FSFC.visit(coden)
            fc_SurNode = FSFC.result

            if fc_SurNode != None and fc_SurNode not in stack:
                stack.add(fc_SurNode)
                root.body.insert(
                    0, fc_SurNode
                )  # Add the function declaration to the top

                # there might addignitional unassigned variables caused by the new function
                FCV = UnusedVars()
                FCV.visit(fc_SurNode)
                _, fc_UAVs = Vars(FCV.assigned, FCV.used)
                target_names = target_names.union(fc_UAVs[fc_SurNode.name]) - exceptions

                continue

        # No duplicate
        if SurNode in stack:
            continue

        # There really doesn't exist the variable in the code => Further search for Imports
        if SurNode == None:
            remains.add(nv)
            continue

        # Find a node using an variable
        MUVC = llm_pre.ModUseVars(mappings, FuncDefs, ParentO, name)
        SurNode = MUVC.visit(SurNode)

        # Find the index of the statement that uses nv at the first

        for node in ast.walk(root):
            if isinstance(SurNode, ast.Assign):
                return_first_index(nv, gp, SurNode, nodeo, noden)
                break

            elif isinstance(SurNode, ast.With) or isinstance(
                SurNode, ast.AsyncWith
            ):  # SurNode can be with or asyncwith
                SurNode = with_sur(nv, SurNode, gp)
                break

            else:
                print("not gonna happen")

        VarsN = UnusedVars()
        VarsN.visit(root)

        target_names = target_names | (
            (Vars(VarsN.assigned, VarsN.used)[1][name]) - exceptions
        )

        stack.add(SurNode)

        SurNodes = SurNodes.union(stack)

    return (root, SurNodes, remains)


class UnusedVars(ast.NodeVisitor):
    def __init__(self, libo=None, name="module"):
        self.name = name

        self.unassigned = {"module": set()}
        self.unused = {"module": set()}

        self.assigned = {"module": set()}
        self.used = {"module": set()}

        self.imports = set()
        self.libo = libo

        self.check = False

    def visit_FunctionDef(self, node: ast.FunctionDef):
        t_name = self.name
        self.name = node.name

        if node.name not in self.unassigned:
            self.unassigned[node.name] = set()

        if node.name not in self.unused:
            self.unused[node.name] = set()

        if node.name not in self.assigned:
            self.assigned[node.name] = set()

        if node.name not in self.used:
            self.used[node.name] = set()

        # should add decorator
        for decorator in node.decorator_list:
            self.visit(decorator)

        # Adding arguments in tmp_assigned
        self.visit(node.args)

        for stmt in node.body:
            self.visit(stmt)

        self.name = t_name

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        t_name = self.name
        self.name = node.name

        if node.name not in self.unassigned:
            self.unassigned[node.name] = set()

        if node.name not in self.unused:
            self.unused[node.name] = set()

        if node.name not in self.assigned:
            self.assigned[node.name] = set()

        if node.name not in self.used:
            self.used[node.name] = set()

        # should add decorator
        for decorator in node.decorator_list:
            self.visit(decorator)

        # Adding arguments in tmp_assigned
        self.visit(node.args)

        for stmt in node.body:
            self.visit(stmt)

        self.name = t_name

    def visit_ClassDef(self, node: ast.ClassDef):
        # When unassigned variable is in base of class node, its scope is in 'module'
        for base in node.bases:
            self.visit(base)

        t_name = self.name
        self.name = node.name

        if node.name not in self.unassigned.keys():
            self.unassigned[node.name] = set()

        if node.name not in self.unused.keys():
            self.unused[node.name] = set()

        if node.name not in self.assigned.keys():
            self.assigned[node.name] = set()

        if node.name not in self.used.keys():
            self.used[node.name] = set()

        for decorator in node.decorator_list:
            self.visit(decorator)

        for stmt in node.body:
            self.visit(stmt)

        self.name = t_name

    def visit_Return(self, node: ast.Return):
        if node.value != None:
            self.visit(node.value)

    def visit_Delete(self, node: ast.Delete):
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        self.visit(node.value)

        self.check = True

        for target in node.targets:
            if isinstance(target, ast.Name):
                self.visit(target)

            if (
                isinstance(target, ast.Attribute)
                and "self" in ast.unparse(target)
                and isinstance(target.value, ast.Name)
            ):
                try:
                    self.assigned[self.name].add(ast.unparse(target))

                except:
                    self.assigned[self.name] = set()
                    self.assigned[self.name].add(ast.unparse(target))

            elif isinstance(target, ast.Attribute):
                self.check = False
                self.visit(target)
                self.check = True

            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        self.visit(elt)

                    elif isinstance(elt, ast.Attribute):
                        self.check = False
                        self.visit(elt)
                        self.check = True

                    else:
                        self.visit(elt)

        self.check = False

    def visit_AugAssign(self, node: ast.AugAssign):
        self.visit(node.value)

        self.check = True
        self.visit(node.target)
        self.check = False

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value != None:
            self.visit(node.value)

        self.check = True
        self.visit(node.target)
        self.check = False

    def visit_For(self, node: ast.For):
        self.visit(node.iter)

        self.check = True
        self.visit(node.target)
        self.check = False

        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self.visit(node.iter)

        self.check = True
        self.visit(node.target)
        self.check = False

        for stmt in node.body:
            self.visit(stmt)

    def visit_While(self, node: ast.While):
        self.visit(node.test)

        for stmt in node.body:
            self.visit(stmt)

        for stmt in node.orelse:
            self.visit(stmt)

    def visit_If(self, node: ast.If):

        self.visit(node.test)

        for stmt in node.body:
            self.visit(stmt)

        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With):
        for item in node.items:
            self.visit(item.context_expr)

            if item.optional_vars != None:
                self.check = True
                self.visit(item.optional_vars)
                self.check = False

        for stmt in node.body:
            self.visit(stmt)

    def visit_AsyncWith(self, node: ast.AsyncWith):
        for item in node.items:
            self.visit(item.context_expr)

            if item.optional_vars != None:
                self.check = True
                self.visit(item.optional_vars)
                self.check = False

        for stmt in node.body:
            self.visit(stmt)

    def visit_Match(self, node: ast.Match):
        pass
        # print('Match is not supported yet')

    def visit_Raise(self, node: ast.Raise):
        pass
        # print('Raise is not supported yet')

    def visit_Try(self, node: ast.Try):
        for stmt in node.body:
            self.visit(stmt)

        for handler in node.handlers:
            self.visit(handler)

        for stmt in node.orelse:
            self.visit(stmt)

        for stmt in node.finalbody:
            self.visit(stmt)

    def visit_Assert(self, node: ast.Assert):
        self.visit(node.test)

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            # May old api and new api have same name
            if ((self.libo != None) and (self.libo not in (alias.name))) or (
                self.libo == None
            ):
                if alias.asname != None:
                    self.imports.add(alias.asname)
                else:
                    self.imports.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        # May old api and new api have same name
        if (
            (self.libo != None)
            and (node.module != None)
            and (self.libo not in node.module)
        ) or (self.libo == None):
            for alias in node.names:
                if alias.asname != None:
                    self.imports.add(alias.asname)
                else:
                    self.imports.add(alias.name)

    def visit_Global(self, node: ast.Global):
        print("Global is not supported yet")

    def visit_Nonlocal(self, node: ast.Nonlocal):
        print("Nonlocal is not supported yet")

    def visit_Expr(self, node: ast.Expr):
        self.visit(node.value)

    # Other expression needs only visit

    # def visit_BoolOp(self, node: ast.BoolOp):

    def visit_NamedExpr(self, node: ast.NamedExpr):
        self.visit(node.value)

        self.check = True
        self.visit(node.target)
        self.check = False

    # def visit_BinOp(self, node: ast.BinOp):
    # def visit_UnaryOp(self, node: ast.UnaryOp):

    def visit_Lambda(self, node: ast.Lambda):
        self.check = True
        self.visit(node.args)
        self.check = False
        self.visit(node.body)

    # def visit_IfExp(self, node: ast.IfExp):
    # def visit_Dict(self, node: ast.Dict):
    # def visit_Set(self, node: ast.Set):

    def visit_ListComp(self, node: ast.ListComp):
        for generator in node.generators:
            self.visit(generator)

        self.visit(node.elt)

    def visit_SetComp(self, node: ast.SetComp):
        for generator in node.generators:
            self.visit(generator)

        self.visit(node.elt)

    def visit_Dictcomp(self, node: ast.DictComp):
        for generator in node.generators:
            self.visit(generator)

        self.visit(node.key)
        self.visit(node.value)

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        for generator in node.generators:
            self.visit(generator)

        self.visit(node.elt)

    # def visit_Await(self, node: ast.Await):
    # def visit_Yield(self, node: ast.Yield):
    # def YieldFrom(self, node: ast.YieldFrom):

    # def visit_Compare(self, node: ast.Compare):
    # def visit_Call(self, node: ast.Call):
    #     self.visit(node.func)
    #     self.

    # def visit_FormattedValue(self, node: ast.FormattedValue):
    # def visit_JoinedStr(self, node: ast.JoinedStr):
    # def visit_Constant(self, node: ast.Constant):

    def visit_Attribute(self, node: ast.Attribute):
        # Used for looking for assigned variables
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and self.check
            and isinstance(node.ctx, ast.Load)
        ):
            try:
                self.assigned[self.name].add("self." + node.attr)
            except:
                self.assigned[self.name] = {"self." + node.attr}

        elif (
            isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and (not self.check)
            and isinstance(node.ctx, ast.Load)
        ):
            if "self." + node.attr not in self.assigned[self.name]:
                try:
                    self.unassigned[self.name].add("self." + node.attr)
                except:
                    self.unassigned[self.name] = {"self." + node.attr}

            try:
                self.used[self.name].add("self." + node.attr)
            except:
                self.used[self.name] = {"self." + node.attr}

        else:
            if not self.check:
                try:
                    self.used[self.name].add((node.attr))
                except:
                    self.used[self.name] = {node.attr}

            self.visit(node.value)

    # def visit_Subscript(self, node: ast.Subscript):
    # def visit_Starred(self, node: ast.Starred):

    def visit_Name(self, node: ast.Name):
        if node.id != "self":
            # Used for looking for assigned variables
            if self.check:
                try:
                    self.assigned[self.name].add(node.id)
                except:
                    self.assigned[self.name] = {node.id}

            else:
                # if assign is false, it is used for looking for used variables
                if node.id not in self.assigned[self.name]:
                    try:
                        self.unassigned[self.name].add(node.id)
                    except:
                        self.unassigned[self.name] = {node.id}

                try:
                    self.used[self.name].add(node.id)
                except:
                    self.used[self.name] = {node.id}

    # def visit_List(self, node: ast.List):

    def visit_Tuple(self, node: ast.Tuple):
        self.generic_visit(node)

    # def visit_Slice(self, node: ast.Slice):

    def visit_comprehension(self, node: ast.comprehension):
        self.check = True
        self.visit(node.target)
        self.check = False

        self.visit(node.iter)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if node.type != None:
            self.visit(node.type)

        if node.name != None:
            try:
                self.assigned[self.name].add(node.name)
            except:
                self.assigned[self.name] = {node.name}

        for stmt in node.body:
            self.visit(stmt)

    def visit_arguments(self, node: ast.arguments):
        for posonlyarg in node.posonlyargs:

            if posonlyarg.arg != "self":
                try:
                    self.assigned[self.name].add(posonlyarg.arg)
                except:
                    self.assigned[self.name] = {posonlyarg.arg}

                if posonlyarg.annotation != None:
                    try:
                        self.used[self.name].add(posonlyarg.annotation)
                    except:
                        self.used[self.name] = {posonlyarg.annotation}

        for arg in node.args:
            if arg.arg != "self":
                try:
                    self.assigned[self.name].add(arg.arg)
                except:
                    self.assigned[self.name] = {arg.arg}

                if arg.annotation != None:
                    try:
                        if isinstance(arg.annotation, ast.Name):
                            self.used[self.name].add(arg.annotation.id)
                        if isinstance(arg.annotation, ast.Attribute):
                            self.visit(arg.annotation)
                    except:
                        if isinstance(arg.annotation, ast.Name):
                            self.used[self.name] = {arg.annotation.id}
                        if isinstance(arg.annotation, ast.Attribute):
                            self.visit(arg.annotation)
                        # self.used[self.name] = {arg.annotation}

        for kwonlyarg in node.kwonlyargs:
            if kwonlyarg.arg != "self":
                try:
                    self.assigned[self.name].add(kwonlyarg.arg)
                except:
                    self.assigned[self.name] = {kwonlyarg.arg}

                if kwonlyarg.annotation != None:
                    try:
                        self.used[self.name].add(kwonlyarg.annotation)
                    except:
                        self.used[self.name] = {kwonlyarg.annotation}

        if node.vararg != None:
            if node.vararg.arg != "self":
                try:
                    self.assigned[self.name].add(node.vararg.arg)
                except:
                    self.assigned[self.name] = {node.vararg.arg}

                if node.vararg.annotation != None:
                    try:
                        self.used[self.name].add(node.vararg.annotation)
                    except:
                        self.used[self.name] = {node.vararg.annotation}

    # def visit_arg(self, node: ast.arg):
    # def visit_keyword(self, node: ast.keyword):
    # def visit_alias(self, node: ast.alias):
    # def visit_withitem(self, node: ast.withitem):
    ## def visit_match_case(self, node: ast.match_case): Not supported yet


# stmt 받아서 그게 특정한 name 노드를 사용하는지 확인
class NameBool(ast.NodeVisitor):
    def __init__(
        self, name: dict[str : set[str]], ctx: ast.expr_context, depth, usedvars=None
    ):
        self.name = name
        self.ctx = ctx
        self.found = False
        self.depth = depth
        self.usedvars = usedvars

    def visit_Name(self, node: ast.Name):
        for key, val in self.name.items():
            if node.id in val and isinstance(node.ctx, self.ctx) and self.depth == key:
                self.found = True

    def visit_Attribute(self, node: ast.Attribute):
        upnode = ast.unparse(node)
        tmp1 = True

        for key, val in self.name.items():
            if upnode in val and isinstance(node.ctx, self.ctx) and self.depth == key:
                self.found = True

        if self.usedvars != None:
            for key, val in self.usedvars.items():
                if upnode in val and isinstance(
                    node.ctx, self.ctx
                ):  # self.depth does not matter ...
                    tmp1 = False

        self.found = self.found and tmp1


def AliasBool(names: list[str], alias: alias):
    target = alias.asname or alias.name
    if target in names:
        return True
    else:
        return False


def NameBoolExc(
    name: dict, ctx: ast.expr_context, code: ast.AST, depth: str, usedvars=None
) -> bool:
    if type(code) == list:
        # Unuse var?
        for stmt in code:
            tmp = NameBool(name, ctx, depth, usedvars=usedvars)
            tmp.visit(stmt)
            return tmp.found

    elif code != None:
        tmp = NameBool(name, ctx, depth, usedvars=usedvars)
        tmp.visit(code)
        return tmp.found

    else:
        return False


# self name에 맞춰서 거기에 있는 거만 변수명 지우기
class SynthDel(ast.NodeTransformer):
    def __init__(
        self,
        ONs: list[ast.stmt],
        UnAssVars: dict,
        UnUseVars: dict,
        history=None,
        replace=False,
        replacenode=None,
        usedvars=None,
        dec=False,
    ) -> ast.AST:
        self.ONs = ONs
        self.UnAssVars = UnAssVars
        self.UnUseVars = UnUseVars
        self.history = history
        self.name = "module"
        self.replace = replace
        self.replacenode: ast.Assign = replacenode
        self.usedvars = usedvars
        self.dec = dec

    def visit_Call(self, node: ast.Call):  # Usually Decorator Node
        if (node in self.ONs) and self.dec:
            return None
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old = self.name
        self.name = node.name  # function name
        tmp = self.generic_visit(node)
        self.name = old
        return tmp

    def visit_AsyncFunctionDef(self, node: AsyncFunctionDef):
        old = self.name
        self.name = node.name  # function name
        tmp = self.generic_visit(node)
        self.name = old
        return tmp

    def visit_Return(self, node: Return):
        if node in self.ONs and node not in self.history:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.value, self.name, usedvars=self.usedvars
        ):
            return None
        else:
            return self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.name = node.name
        return self.generic_visit(node)

    def visit_Delete(self, node: Delete):
        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node, self.name, usedvars=self.usedvars
        ):
            return None
        else:
            return self.generic_visit(node)

    def visit_Assign(self, node: Assign):
        if self.replace and node in self.ONs:  # if replacing
            ovalue = node.value
            nvalue = self.replacenode.value
            if ("json" in ast.unparse(ovalue)) and (
                "json" in ast.unparse(nvalue)
            ):  # added ??
                node.value = nvalue
                return node

        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.value, self.name, usedvars=self.usedvars
        ):
            return None
        elif (
            NameBoolExc(
                self.UnUseVars,
                ast.Store,
                node.targets,
                self.name,
                usedvars=self.usedvars,
            )
        ) and not (
            NameBoolExc(self.usedvars, ast.Store, node.targets, self.name)
        ):  # latter cond is for multiple assignment
            return None
        else:
            return self.generic_visit(node)

    def visit_AnnAssign(self, node: AnnAssign):
        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.value, self.name, usedvars=self.usedvars
        ):
            return None
        else:
            return self.generic_visit(node)

    def visit_For(self, node: For):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_AsyncFor(self, node: AsyncFor):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_While(self, node: While):
        if node in self.ONs:
            return None
        elif node.test in self.ONs:
            node.test = ast.Constant(value=True)
            return node
        else:
            return self.generic_visit(node)

    def visit_If(self, node: If):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_With(self, node: With):
        if (node in self.ONs) or (
            NameBoolExc(
                self.UnAssVars, ast.Load, node.items, self.name, usedvars=self.usedvars
            )
        ):
            body1 = []

            for b in node.body:
                tmp = SynthDel(self.ONs, self.UnAssVars, self.UnUseVars)
                b1 = tmp.visit(b)
                if b1 != None:
                    body1.append(b1)

            return ast.Module(body=body1, type_ignores=[])

        else:
            return self.generic_visit(node)

    def visit_AsyncWith(self, node: AsyncWith):
        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.items, self.name, usedvars=self.usedvars
        ):
            return ast.Module(body=node.body, type_ignores=[])
        else:
            return self.generic_visit(node)

    def visit_Raise(self, node: Raise):
        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.exc, self.name, usedvars=self.usedvars
        ) or NameBoolExc(
            self.UnAssVars, ast.Load, node.cause, self.name, usedvars=self.usedvars
        ):
            return None
        else:
            return self.generic_visit(node)

    def visit_Try(self, node: Try):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_Assert(self, node: Assert):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        if node in self.ONs:
            return ast.Pass()
        else:
            tmp = node.names
            for name in node.names:

                if AliasBool(self.UnUseVars, name):
                    tmp.remove(name)

            if len(tmp) == 0:
                return ast.Pass()
            else:
                node.names = tmp
                return node

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node in self.ONs:
            return ast.Pass()
        else:
            tmp = node.names
            for name in node.names:

                if AliasBool(self.UnUseVars, name):
                    tmp.remove(name)

            if len(tmp) == 0:
                return ast.Pass()
            else:
                node.names = tmp
                return node

    def visit_Global(self, node: Global):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_Nonlocal(self, node: Nonlocal):
        if node in self.ONs:
            return None
        else:
            return self.generic_visit(node)

    def visit_Expr(self, node: Expr):
        if node in self.ONs:
            return None
        elif NameBoolExc(
            self.UnAssVars, ast.Load, node.value, self.name, usedvars=self.usedvars
        ):

            return None
        else:
            return self.generic_visit(node)
