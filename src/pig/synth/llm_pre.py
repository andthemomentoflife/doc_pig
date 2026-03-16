import ast, sys
from os import path
from typing import Union

sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
from pig.slicing import slicing
from mapping.gits import GIT_LOC

try:
    from .stmt_types import stmt as stmt_type, Stmtyp
except:
    from stmt_types import stmt as stmt_type, Stmtyp

try:
    from .stmt_types import expr as expr_type
except:
    from stmt_types import expr as expr_type

try:
    import matching
except:
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
    import matching

try:
    import call, synthesis
except:
    from . import call, synthesis

stmtInstmt = [
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Module,
]
stmtInFuncClass = [ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef]
stmtInstmt1 = [
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.If,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Module,
    ast.ExceptHandler,
    ast.match_case,
]


def scope_name(nodeo, noden, parent):
    """Return the name of the enclosing function or class scope for a node.

    Determines the appropriate scope by inspecting ``noden``: if the new node
    is itself a function or class definition, the search starts two levels up
    from ``nodeo``; otherwise it starts one level up. The scope name is
    resolved via :func:`slicing.extract_name`.

    :param nodeo: The original AST node whose enclosing scope is to be found.
    :type nodeo: ast.AST
    :param noden: The new AST node used to decide the traversal depth.
    :type noden: ast.AST
    :param parent: The parent mapping as produced by :func:`call.ParentAst`.
    :type parent: dict
    :return: The name of the enclosing function, class, or ``'module'`` if
        the traversal reaches the module root.
    :rtype: str | None
    """
    if isinstance(noden, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        FCP = call.FindFCParent(parent, nodeo, 2)
    else:
        FCP = call.FindFCParent(parent, nodeo)

    name = slicing.extract_name(FCP)

    return name


def DupImpSolver(code: ast.Module) -> ast.AST:
    """Remove duplicate import statements and reinsert them as deduplicated entries.

    Uses an inner :class:`ast.NodeTransformer` (``ImpDupRemover``) to strip
    all :class:`ast.Import` and :class:`ast.ImportFrom` nodes from the module
    body while collecting their unique aliases. A second inner helper
    (``ImpDupSolver``) then reinserts the deduplicated imports at the top of
    the module.

    Deduplication is keyed on ``(name, asname)`` for :class:`ast.Import` and
    on ``(module, level)`` → ``{(name, asname), ...}`` for
    :class:`ast.ImportFrom`, so multiple ``from X import a, b`` statements
    for the same module are merged into a single node.

    :param code: The AST module whose import statements are to be deduplicated.
    :type code: ast.Module
    :return: The modified AST module with all duplicate imports removed and
        unique imports reinserted at the top of the module body.
    :rtype: ast.AST
    """

    class ImpDupRemover(ast.NodeTransformer):
        def __init__(self):
            self.imps = set()
            self.impfs = dict()

        def visit_Import(self, node: ast.Import):
            for alias in node.names:
                self.imps.add((alias.name, alias.asname))

            return None

        def visit_ImportFrom(self, node: ast.ImportFrom):
            for alias in node.names:
                try:
                    self.impfs[(node.module, node.level)].add(
                        (alias.name, alias.asname)
                    )
                except:
                    self.impfs[(node.module, node.level)] = {(alias.name, alias.asname)}

            return None

    def ImpDupSolver(code: ast.Module, imps, impfs):
        # ast.Import
        for imp in imps:
            code.body.insert(
                0, ast.Import(names=[ast.alias(name=imp[0], asname=imp[1])])
            )

        # ast.ImportFrom
        for (ik, level), iv in impfs.items():
            lst = []

            for n1, n2 in iv:
                lst.append(ast.alias(name=n1, asname=n2))

            code.body.insert(0, ast.ImportFrom(module=ik, names=lst, level=level))

        return code

    ID = ImpDupRemover()
    ID.visit(code)

    return ImpDupSolver(code, ID.imps, ID.impfs)


def is_async(node: ast.AST) -> bool:
    """Check whether an AST node contains any asynchronous constructs.

    Walks the AST subtree rooted at ``node`` and returns ``True`` if any
    :class:`ast.Await`, :class:`ast.AsyncWith`, or :class:`ast.AsyncFor`
    node is found.

    :param node: The AST node to inspect.
    :type node: ast.AST
    :return: ``True`` if the node contains asynchronous constructs,
        ``False`` otherwise.
    :rtype: bool
    """
    for n in ast.walk(node):
        if isinstance(n, (ast.Await, ast.AsyncWith, ast.AsyncFor)):
            return True
    return False


def libname(libo: str) -> str:
    """Resolve the importable top-level package name for a given library identifier.

    Looks up ``libo`` in the combined git location map (``GIT_LOC``) and derives the importable name from the final
    component of its repository path. A small set of known mismatches between
    PyPI package names and importable names are corrected by hard-coded
    overrides.

    :param libo: The library identifier (typically the PyPI package name) to
        resolve.
    :type libo: str
    :return: The importable top-level package name for ``libo``, or ``libo``
        itself if it cannot be found in the location map.
    :rtype: str
    """
    total_loc = GIT_LOC
    total_loc.update(GIT_LOC)

    if libo in total_loc:
        lib_path: str = total_loc[libo]
        lib_name = lib_path.split("/")[-1].strip()

        if ".py" in lib_name:
            lib_name = lib_name.split(".py")[0]

        # Benchmark errors so manual fixed
        if libo == "slackclient":
            return "slack"
        if libo == "node-semver":
            return "semver"
        if libo == "fabric3":
            return "fabric"
        if libo == "httplib2":
            return "httplib"
        if libo == "RPi.GPIO":
            return libo

        if libo == "ruamel.yaml":
            return libo

        return lib_name

    else:
        return libo


# Find the real parent(type: stmt) of the node
def FindLastExpr(parent: dict, node, depth: int):
    """Find the statement-type ancestor of an expression node at the given depth.

    Traverses the parent mapping upward, skipping intermediate
    expression-type nodes, until a statement-type (``stmt_type``) ancestor
    is reached. Similar to :func:`FindRealParent`, but returns ``node``
    itself (rather than ``None``) if no ancestor is found.

    :param parent: The parent mapping as produced by :func:`ParentAst`,
        mapping each node to the set of its direct children.
    :type parent: dict
    :param node: The AST expression node to start traversal from.
    :type node: ast.AST
    :param depth: The number of statement-level hops to traverse.
        ``depth=1`` returns the immediate statement ancestor of ``node``.
    :type depth: int
    :return: The statement-type ancestor at the requested depth, ``None``
        if an unexpected node type is encountered during traversal, or
        ``node`` itself if no parent is found at all.
    :rtype: ast.AST | None
    """
    for key, value in parent.items():
        if node in value and type(key) in stmt_type and depth == 1:
            return node
        elif node in value and type(key) in stmt_type and depth > 1:
            return FindLastExpr(parent, key, depth - 1)
        elif node in value and type(key) in expr_type:
            return FindLastExpr(parent, key, depth)
        elif node in value:
            print("No Parent Found with input depths.", type(key))
            return None
        else:
            pass  # Node not in value Find for anotherƒ

    print("No Parent Found with input depth.")
    return node


def check_two_sim(roota, rooto, var, noden, rootc, surnodes):
    """Rename a variable in ``noden`` to match its counterpart in the new library code.

    Locates the definition of ``var`` in the old API's AST (``roota``),
    finds the corresponding name in the new library's AST (``rootc``) via
    :func:`matching.matcher1`, and rewrites all :class:`ast.Name` references
    to ``var`` in ``noden`` and ``surnodes`` to use the new name.

    :param roota: The AST of the old API usage context, used to locate the
        definition of ``var``.
    :type roota: ast.AST
    :param rooto: The original source AST (reserved for future use).
    :type rooto: ast.AST
    :param var: The variable name to look up and potentially rename.
    :type var: str
    :param noden: The primary AST node in which ``var`` references are to be
        rewritten.
    :type noden: ast.AST
    :param rootc: The unparsed source string of the new library's AST,
        used as the rename target by :func:`matching.matcher1`.
    :type rootc: str
    :param surnodes: Additional AST nodes in which ``var`` references are
        also rewritten if a new name is found.
    :type surnodes: list[ast.AST]
    :return: ``True`` if at least one reference to ``var`` was renamed,
        ``False`` otherwise.
    :rtype: bool
    """
    rootc = ast.parse(rootc)

    # Check Target Names
    def check_targets(node, var: str) -> tuple:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var:
                    return (node, ast.Assign)
                elif isinstance(target, ast.Attribute) and ast.unparse(target) == var:
                    # self
                    return (node, ast.Assign)

                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name) and elt.id == var:
                            return (node, ast.Assign)
                        elif isinstance(elt, ast.Attribute) and ast.unparse(elt) == var:
                            # self
                            return (node, ast.Assign)

        if isinstance(node, ast.Global):
            for name in node.names:
                if name == var:
                    return (node, ast.Global)

        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
        ):
            return (node, ast.AugAssign)

        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
        ):
            return (node, ast.AnnAssign)

        # With일수도 있음
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if (
                    (item.optional_vars != None)
                    and (isinstance(item.optional_vars, ast.Name))
                    and (item.optional_vars.id == var)
                ):
                    return (item.context_expr, type(node))

        return (None, None)

    # Find the node that contains the variable
    def find(code, var):
        for node in ast.walk(code):
            val, _ = check_targets(node, var)
            if val != None:
                return val

        return None  # something wrong

    val_n = find(roota, var)

    if val_n != None:
        changed = False
        newname = matching.matcher1(ast.unparse(roota), ast.unparse(rootc), val_n)
        if newname != None and newname != False:
            # Change the name of the node
            for n in ast.walk(noden):
                if isinstance(n, ast.Name) and n.id == var:
                    n.id = newname
                    changed = True

            for surnode in surnodes:
                for n in ast.walk(surnode):
                    if isinstance(n, ast.Name) and n.id == var:
                        n.id = newname
                        changed = True

        if changed:
            return True

    return False


def extract_var_map(nodeo, noden, codeo: ast.AST, coden: ast.AST, parento, b0=False):
    """Build a variable rename mapping between old and new API usage nodes.

    Compares the variables used in ``nodeo`` (old API) and ``noden`` (new API)
    via :class:`ExtractVarMap` and filters the raw candidates down to a
    mapping of ``{old_name: new_name}`` pairs that represent genuine renames.

    Filtering is handled by four inner helpers:

    - ``check_text_sim(var1, var2)``: accepts a pair if their string
      similarity exceeds 0.5 or one is a substring of the other.
    - ``check_ast_sim(var1, var2, codeo, coden)``: locates the assignment
      nodes for each variable and delegates to :func:`matching.single_matcher`
      to confirm structural similarity.
    - ``check_targets(node, var)``: searches a single AST node for an
      assignment to ``var``, handling :class:`ast.Assign`,
      :class:`ast.AugAssign`, :class:`ast.AnnAssign`, and
      :class:`ast.With` targets.
    - ``filter(codeo, coden, v1, parento, nodeo)``: excludes pairs where
      the variable is defined in both the old and new code within the same
      scope, indicating it is not a rename but a shared local name.

    When ``b0`` is ``True``, only AST-similarity is used and constant
    assignments that directly match their value in the old code are excluded.
    When ``b0`` is ``False``, both text and AST similarity are applied
    alongside the scope filter.

    :param nodeo: The old API AST node whose variable references are the
        source of the mapping.
    :type nodeo: ast.AST
    :param noden: The new API AST node whose variable references are the
        rename targets.
    :type noden: ast.AST
    :param codeo: The full old code AST, used to locate variable definitions
        for similarity checks.
    :type codeo: ast.AST
    :param coden: The full new code AST, used to locate variable definitions
        for similarity checks.
    :type coden: ast.AST
    :param parento: The parent mapping of the old code as produced by
        :func:`call.ParentAst`, used for scope resolution.
    :param b0: If ``True``, apply AST-similarity-only filtering suitable for
        direct API node comparisons. If ``False``, apply the full text and
        AST similarity pipeline with scope filtering. Defaults to ``False``.
    :type b0: bool
    :return: A mapping from each old variable name to its corresponding new
        variable name.
    :rtype: dict[str, str]
    """
    mapping = dict()

    def check_text_sim(var1: str, var2: str) -> bool:
        from difflib import SequenceMatcher

        if not isinstance(var1, str) or not isinstance(var2, str):
            return False

        sim = SequenceMatcher(None, var1, var2).ratio()

        cond1 = sim > 0.5  # how can I set this threshold?
        cond2 = (var1.lower() in var2.lower()) or (var2.lower() in var1.lower())

        return cond1 or cond2

    # Find the node that contains the variable
    def find(code, var):
        for node in ast.walk(code):
            val, _ = check_targets(node, var)
            if val != None:
                return val

        return None  # something wrong

    # Check Target Names
    def check_targets(node, var: str) -> tuple:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var:
                    return (node, ast.Assign)
                elif isinstance(target, ast.Attribute) and ast.unparse(target) == var:
                    # self
                    return (node, ast.Assign)

                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name) and elt.id == var:
                            return (node, ast.Assign)
                        elif isinstance(elt, ast.Attribute) and ast.unparse(elt) == var:
                            # self
                            return (node, ast.Assign)

        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
        ):
            return (node, ast.AugAssign)

        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == var
        ):
            return (node, ast.AnnAssign)

        # With일수도 있음
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if (
                    (item.optional_vars != None)
                    and (isinstance(item.optional_vars, ast.Name))
                    and (item.optional_vars.id == var)
                ):
                    return (item.context_expr, type(node))

        return (None, None)

    def check_ast_sim(var1: str, var2: str, codeo: ast.AST, coden: ast.AST) -> bool:
        # 1. Find variable assign nodes
        val_o: Union[ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expression, None] = (
            find(codeo, var1)
        )
        val_n: Union[ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expression, None] = (
            find(coden, var2)
        )

        # try:
        #     print(ast.unparse(val_o), ast.unparse(val_n), var1, var2)
        # except:
        #     print("Error in unparse", val_o, val_n, var1, var2)

        if val_o and val_n:
            codeo = ast.fix_missing_locations(codeo)
            coden = ast.fix_missing_locations(coden)

            return matching.single_matcher(
                ast.unparse(codeo), ast.unparse(coden), val_o, val_n, coden
            )
        else:
            return False

    # key: self.__sftp_client.put(script_file, script_name) val: put(script_file, '/tmp/scripts/{0}'.format(script_name))
    # {'script_file': 'script_name'} mappings
    def filter(codeo: ast.AST, coden: ast.AST, v1, parento, nodeo) -> bool:

        def find_filter(code, var: str, parent, fname: str):
            for node in ast.walk(code):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == var:
                            return True

                if (
                    isinstance(node, ast.AugAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == var
                ):
                    return True

                if (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and node.target.id == var
                ):
                    return True

                if isinstance(node, (ast.With, ast.AsyncWith)):
                    for item in node.items:
                        if (
                            (item.optional_vars != None)
                            and (isinstance(item.optional_vars, ast.Name))
                            and (item.optional_vars.id == var)
                        ):
                            return True

                if isinstance(node, ast.arg):
                    # Scope should be considred
                    FCP = call.FindFCParent(parent, node)
                    name = slicing.extract_name(FCP)

                    if (node.arg == var) and (name == fname):
                        return True

            return False

        fname = slicing.extract_name(call.FindFCParent(parento, nodeo))

        val1 = find_filter(codeo, v1, parento, fname)
        val2 = find_filter(coden, v1, parento, fname)

        return val1 and val2

    # Code
    # 1. Find variable mapping candidates through ast matching
    EVMC = ExtractVarMap(noden)
    EVMC.visit(nodeo)
    mapping: dict = EVMC.mapping
    result: dict = dict()

    # Filter only it's not a direct node match (api 대상끼리 매칭된건 당연히 전후 변화가 없을거기때문에 지들끼리 매칭되는게마즘)
    if b0:
        # 근데 원래 있는 애들이면 안됨 # key not in mapi;ng
        for key, val in mapping.items():
            if isinstance(key, ast.Constant):
                pass

            elif isinstance(val, ast.Constant):
                # Find whether the variable is directly changed with Constant
                # key would be ast.Name
                tmp_b = False

                for __node in ast.walk(codeo):
                    if isinstance(__node, ast.Assign):
                        for target in __node.targets:
                            if isinstance(target, ast.Name) and target.id == key:
                                # Check for value

                                if isinstance(__node.value, ast.Constant):
                                    if __node.value.value == val:
                                        tmp_b = True

                if not tmp_b:
                    result[key] = val

            elif (
                key != val
                and val not in mapping
                and check_ast_sim(key, val, codeo, coden)
            ):
                result[key] = val

            else:
                pass

    else:
        # 2. Filter candidates based on 1) text sim 2) ast sim
        for key, val in mapping.items():
            cond0 = check_text_sim(key, val) or check_ast_sim(key, val, codeo, coden)
            cond1 = not filter(codeo, coden, key, parento, nodeo)

            if cond0 and cond1 and (key != val):
                result[key] = val

    # 3. Return the final mapping
    return result


class ExtractVarMap(ast.NodeVisitor):
    def __init__(self, nodeo):
        self.nodeo = nodeo
        self.mapping = dict()
        self.check = True

    # def visit_FunctionDef(self, node: ast.FunctionDef):
    # def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
    # def visit_ClassDef(self, node: ast.ClassDef):

    def visit_Return(self, node: ast.Return):
        if isinstance(self.nodeo, ast.Return):
            self.nodeo = self.nodeo.value
            self.visit(node.value)
        else:
            self.check = False

    # def visit_Delete(self, node: ast.Delete):

    def peel_off(self, node1, node2):
        # ignore

        while isinstance(node1, (ast.Expr, ast.Await)):
            node1 = node1.value
        while isinstance(node2, (ast.Expr, ast.Await)):
            node2 = node2.value

        return node1, node2

    def visit_Assign(self, node: ast.Assign):
        # Support Only there's one target
        if isinstance(self.nodeo, ast.Assign):
            if len(node.targets) == 1 and len(self.nodeo.targets) == 1:
                if isinstance(self.nodeo.targets[0], ast.Name) and isinstance(
                    node.targets[0], ast.Name
                ):
                    if node.targets[0].id != self.nodeo.targets[0].id and self.check:
                        self.mapping[node.targets[0].id] = self.nodeo.targets[0].id

                if isinstance(self.nodeo.targets[0], ast.Attribute) and isinstance(
                    node.targets[0], ast.Attribute
                ):
                    tmp = self.nodeo
                    self.nodeo = self.nodeo.targets[0]
                    self.visit(node.targets[0])
                    self.nodeo = tmp

            tmp = self.nodeo
            self.nodeo = self.nodeo.value

            _node, self.nodeo = self.peel_off(node.value, self.nodeo)
            self.visit(_node)
            self.nodeo = tmp

        elif isinstance(self.nodeo, (ast.With, ast.AsyncWith)):
            # len 제한을 두어야 할까? 그러니까 무조건 일대일 대응...
            tmp = self.nodeo

            for item in self.nodeo.items:
                if (item.optional_vars != None) and (
                    isinstance(item.optional_vars, ast.Name)
                ):
                    self.nodeo = item.optional_vars
                    self.visit(node.targets[0])

                self.nodeo = item.context_expr
                self.visit(node.value)

            self.nodeo = tmp

        else:
            self.check = False

    # def visit_TypeAlias(self, node: ast.TypeAlias):

    def visit_AugAssign(self, node: ast.AugAssign):
        if isinstance(self.nodeo, ast.AugAssign) and (node.op == self.nodeo.op):
            self.mapping[node.target.id] = self.nodeo.target.id
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        else:
            self.check = False

    # def visit_For(self, node: ast.For):
    # def visit_AsyncFor(self, node: ast.AsyncFor):
    # def visit_While(self, node: ast.While):
    # def visit_If(self, node: ast.If):

    def visit_With(self, node: ast.With):
        if isinstance(self.nodeo, (ast.With, ast.AsyncWith)):
            if len(node.items) == len(self.nodeo.items):
                tmp = self.nodeo

                for i in range(len(node.items)):
                    item_o = self.nodeo.items[i]
                    item_n = node.items[i]

                    # Usually With or AsyncWith has only one withitem
                    if (item_o.optional_vars != None) and item_n.optional_vars != None:
                        self.nodeo = item_o.optional_vars
                        self.visit(item_n.optional_vars)

                    self.nodeo = item_o.context_expr
                    self.visit(item_n.context_expr)

                self.nodeo = tmp

        elif isinstance(self.nodeo, ast.Assign):
            tmp = self.nodeo

            # len 안 맞춰도 되나?
            for item in node.items:
                if item.optional_vars != None:
                    self.nodeo = item.optional_vars
                    self.visit(tmp.targets[0])

                self.nodeo = item.context_expr
                self.visit(tmp.value)

            self.nodeo = tmp

        else:
            self.check = False

    def visit_AsyncWith(self, node: ast.AsyncWith):
        if isinstance(self.nodeo, (ast.With, ast.AsyncWith)):
            if len(node.items) == len(self.nodeo.items):
                tmp = self.nodeo

                for i in range(len(node.items)):
                    item_o = self.nodeo.items[i]
                    item_n = node.items[i]

                    # Usually With or AsyncWith has only one withitem
                    if (item_o.optional_vars != None) and item_n.optional_vars != None:
                        self.nodeo = item_o.optional_vars
                        self.visit(item_n.optional_vars)

                    self.nodeo = item_o.context_expr
                    self.visit(item_n.context_expr)

                self.nodeo = tmp

        elif isinstance(self.nodeo, ast.Assign):
            tmp = self.nodeo

            # len 안 맞춰도 되나?
            for item in node.items:
                if item.optional_vars != None:
                    self.nodeo = item.optional_vars
                    self.visit(tmp.targets[0])

                self.nodeo = item.context_expr
                self.visit(tmp.value)

            self.nodeo = tmp

        else:
            self.check = False

    # def visit_Match(self, node: ast.Match):
    # def visit_Raise(self, node: ast.Raise):
    # def visit_Try(self, node: ast.Try):

    def visit_Assert(self, node: ast.Assert):
        if isinstance(self.nodeo, ast.Assert):
            self.nodeo = self.nodeo.test
            self.visit(node.test)

        else:
            self.check = False

    # def visit_Import(self, node: ast.Import):
    # def visit_ImportFrom(self, node: ast.ImportFrom):

    # def visit_Global(self, node: ast.Global):
    # def visit_Nonlocal(self, node: ast.Nonlocal):

    def visit_Expr(self, node: ast.Expr):
        if isinstance(self.nodeo, ast.Expr):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        elif type(node.value) == type(self.nodeo):
            self.visit(node.value)

        elif isinstance(self.nodeo, ast.Assign):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        elif isinstance(self.nodeo, ast.Await):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        else:
            self.check = False

    # def visit_Pass(self, node: ast.Pass):
    # def visit_Break(self, node: ast.Break):
    # def visit_Continue(self, node: ast.Continue):

    def visit_BoolOp(self, node: ast.BoolOp):
        if (
            isinstance(self.nodeo, ast.BoolOp)
            and (node.op == self.nodeo.op)
            and len(node.values) == len(self.nodeo.values)
            and len(node.values) == 1
        ):
            self.nodeo = self.nodeo.values[0]
            self.visit(node.values[0])

        else:
            self.check = False

    def visit_NamedExpr(self, node: ast.NamedExpr):
        if isinstance(self.nodeo, ast.NamedExpr):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        else:
            self.check = False

    def visit_BinOp(self, node: ast.BinOp):
        if isinstance(self.nodeo, ast.BinOp) and (node.op == self.nodeo.op):
            tmp = self.nodeo
            self.nodeo = self.nodeo.right
            self.visit(node.right)
            self.nodeo = tmp.left
            self.visit(node.left)
            self.nodeo = tmp

        else:
            self.check = False

    def visit_UnaryOp(self, node: ast.UnaryOp):
        if isinstance(self.nodeo, ast.UnaryOp) and (node.op == self.nodeo.op):
            self.nodeo = self.nodeo.operand
            self.visit(node.operand)

        else:
            self.check = False

    def visit_Lambda(self, node: ast.Lambda):
        if isinstance(self.nodeo, ast.Lambda):
            self.nodeo = self.nodeo.body
            self.visit(node.body)

        else:
            self.check = False

    def visit_IfExp(self, node: ast.IfExp):
        if isinstance(self.nodeo, ast.IfExp):
            tmp = self.nodeo
            self.nodeo = self.nodeo.test
            self.visit(node.test)
            self.nodeo = tmp.body
            self.visit(node.body)
            self.nodeo = tmp.orelse
            self.visit(node.orelse)
            # self.nodeo = tmp

        else:
            self.check = False

    def visit_Dict(self, node: ast.Dict):
        # Why only length one -> because llm might change the function order...
        if (
            isinstance(self.nodeo, ast.Dict)
            and (len(node.keys) == len(self.nodeo.keys))
            and (len(node.keys)) == len(node.values)
        ):
            for i in range(len(node.keys)):
                try:
                    self.nodeo = self.nodeo.keys[i]
                    self.visit(node.keys[i])
                except:
                    self.check = False

            for j in range(len(node.values)):
                try:
                    self.nodeo = self.nodeo.values[j]
                    self.visit(node.values[j])
                except:
                    self.check = False

        else:
            self.check = False

    def visit_Set(self, node: ast.Set):
        if (
            isinstance(self.nodeo, ast.Set)
            and (len(node.elts) == len(self.nodeo.elts))
            and len(node.elts) == 1
        ):
            self.nodeo = self.nodeo.elts[0]
            self.visit(node.elts[0])

        else:
            self.check = False

    def visit_ListComp(self, node: ast.ListComp):
        if isinstance(self.nodeo, ast.ListComp):
            tmp = self.nodeo
            self.nodeo = self.nodeo.elt
            self.visit(node.elt)

            if (
                (len(node.generators) == len(tmp.generators))
                and len(node.generators) == 1
                and (type(node.generators[0]) == type(tmp.generators[0]))
            ):
                self.mapping[ast.unparse(node.generators[0].iter)] = ast.unparse(
                    tmp.generators[0].iter
                )

                # self.nodeo = tmp.generators[0]
                # self.visit(node.generators[0])

            else:
                self.check = False

        else:
            self.check = False

    def visit_SetComp(self, node: ast.SetComp):
        if isinstance(self.nodeo, ast.ListComp):
            tmp = self.nodeo
            self.nodeo = self.nodeo.elt
            self.visit(node.elt)

            if (
                (len(node.generators) == len(tmp.generators))
                and len(node.generators) == 1
                and (type(node.generators[0]) == type(tmp.generators[0]))
            ):
                self.mapping[ast.unparse(node.generators[0].iter)] = ast.unparse(
                    tmp.generators[0].iter
                )

            else:
                self.check = False

        else:
            self.check = False

    def visit_DictComp(self, node: ast.DictComp):
        if isinstance(self.nodeo, ast.ListComp):
            tmp = self.nodeo
            self.nodeo = self.nodeo.elt
            self.visit(node.elt)

            if (
                (len(node.generators) == len(tmp.generators))
                and len(node.generators) == 1
                and (type(node.generators[0]) == type(tmp.generators[0]))
            ):
                self.mapping[ast.unparse(node.generators[0].iter)] = ast.unparse(
                    tmp.generators[0].iter
                )

            else:
                self.check = False

        else:
            self.check = False

    def visit_GeneratorExp(self, node: ast.GeneratorExp):
        if isinstance(self.nodeo, ast.GeneratorExp):
            tmp = self.nodeo
            self.nodeo = self.nodeo.elt
            self.visit(node.elt)

            if (len(node.generators) == len(tmp.generators)) and len(
                node.generators
            ) == 1:
                self.nodeo = tmp.generators[0]
                self.visit(node.generators[0])

            else:
                self.check = False

    def visit_Await(self, node: ast.Await):
        if isinstance(self.nodeo, ast.Await):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        elif type(self.nodeo) == type(node.value):
            self.visit(node.value)

        elif isinstance(node.value, ast.Expr) and type(node.value.value) == type(
            self.nodeo
        ):
            self.visit(node.value.value)

        elif isinstance(self.nodeo, ast.Expr) and isinstance(
            self.nodeo.value, ast.Await
        ):
            self.nodeo = self.nodeo.value.value
            self.visit(node.value)

        else:
            self.check = False

    def visit_Yield(self, node: ast.Yield):
        if isinstance(self.nodeo, ast.Yield):
            self.nodeo = self.nodeo.value
            if node.value != None:
                self.visit(node.value)
        else:
            self.check = False

    def visit_YieldFrom(self, node: ast.YieldFrom):
        if isinstance(self.nodeo, ast.YieldFrom):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        else:
            self.check = False

    def visit_Compare(self, node: ast.Compare):
        if isinstance(self.nodeo, ast.Compare) and (
            len(node.ops) == len(self.nodeo.ops)
        ):
            tmp = self.nodeo
            self.nodeo = self.nodeo.left
            self.visit(node.left)

            if (
                len(node.comparators) == len(tmp.comparators)
                and len(node.comparators) == 1
            ):
                self.nodeo = tmp.comparators[0]
                self.visit(node.comparators[0])

            else:
                self.check = False

        else:
            self.check = False

    def visit_Call(self, node: ast.Call):
        save = self.nodeo
        if isinstance(self.nodeo, ast.Call):
            self.nodeo = self.nodeo.func
            self.visit(node.func)
            self.nodeo = save

            if len(node.args) == len(self.nodeo.args):
                for i in range(len(node.args)):
                    for j in range(len(save.args)):
                        # Just put it in name candidates
                        if isinstance(node.args[i], ast.Name) and isinstance(
                            save.args[j], ast.Name
                        ):
                            self.mapping[node.args[i].id] = save.args[j].id

                        elif isinstance(node.args[i], ast.Constant) and isinstance(
                            save.args[j], ast.Name
                        ):
                            self.mapping[node.args[i]] = save.args[j].id
                            # Constant with Name

                        elif isinstance(node.args[i], ast.Name) and isinstance(
                            save.args[j], ast.Constant
                        ):
                            self.mapping[node.args[i].id] = save.args[j]
                            # Name with Constant

                        else:
                            self.nodeo = save.args[j]
                            self.visit(node.args[i])

            self.nodeo = save

            if len(node.keywords) == len(self.nodeo.keywords):
                for i in range(len(node.keywords)):
                    if isinstance(node.keywords[i], ast.keyword):
                        self.nodeo = save
                        if isinstance(self.nodeo.keywords[i], ast.keyword):
                            self.mapping[node.keywords[i].arg] = self.nodeo.keywords[
                                i
                            ].arg

                            if isinstance(
                                node.keywords[i].value, ast.Name
                            ) and isinstance(self.nodeo.keywords[i].value, ast.Name):
                                self.mapping[node.keywords[i].value.id] = (
                                    self.nodeo.keywords[i].value.id
                                )

                            else:
                                self.nodeo = save.keywords[i]
                                self.visit(node.keywords[i])

        elif isinstance(self.nodeo, ast.Expr):
            self.nodeo = self.nodeo.value
            self.visit(node)

        elif isinstance(self.nodeo, ast.Await):
            self.nodeo = self.nodeo.value
            self.visit(node)

        else:
            self.check = False

    def visit_FormattedValue(self, node: ast.FormattedValue):
        if isinstance(self.nodeo, ast.FormattedValue):
            self.nodeo = self.nodeo.value
            self.visit(node.value)

        else:
            self.check = False

    def visit_JoinedStr(self, node: ast.JoinedStr):
        if isinstance(self.nodeo, ast.JoinedStr) and (
            len(node.values) == len(self.nodeo.values)
        ):
            save = self.nodeo

            for i in range(len(node.values)):
                self.nodeo = save.values[i]
                self.visit(node.values[i])

        else:
            self.check = False

    def visit_Constant(self, node: ast.Constant):
        if isinstance(self.nodeo, ast.Constant) and (node.value == self.nodeo.value):
            pass
        else:
            self.check = False

    def visit_Attribute(self, node: ast.Attribute):
        if isinstance(self.nodeo, ast.Attribute):
            if (
                isinstance(self.nodeo.value, ast.Name)
                and isinstance(node.value, ast.Name)
                and (node.value.id == self.nodeo.value.id)
                and (node.value.id == "self")
            ):
                self.mapping[ast.unparse(node)] = ast.unparse(self.nodeo)

            else:
                self.nodeo = self.nodeo.value
                self.visit(node.value)

        else:
            self.check = False

    def visit_Subscript(self, node: ast.Subscript):
        if isinstance(self.nodeo, ast.Subscript):
            tmp = self.nodeo
            self.nodeo = self.nodeo.value
            self.visit(node.value)
            self.nodeo = tmp.slice
            self.visit(node.slice)
        else:
            self.check = False

    def visit_Starred(self, node: ast.Starred):
        self.check = False  # Not supported

    def visit_Name(self, node: ast.Name):
        if isinstance(self.nodeo, ast.Name) and (node.id == self.nodeo.id):
            pass
        elif isinstance(self.nodeo, ast.Name):
            self.mapping[node.id] = self.nodeo.id
        else:
            self.check = False

    def visit_List(self, node: ast.List):
        if (
            isinstance(self.nodeo, ast.List)
            and (len(node.elts) == len(self.nodeo.elts))
            and len(node.elts) == 1
        ):
            self.nodeo = self.nodeo.elts[0]
            self.visit(node.elts[0])

        else:
            self.check = False

    def visit_Tuple(self, node: ast.Tuple):
        if (
            isinstance(self.nodeo, ast.Tuple)
            and (len(node.elts) == len(self.nodeo.elts))
            and len(node.elts) == 1
        ):
            self.nodeo = self.nodeo.elts[0]
            self.visit(node.elts[0])

        else:
            self.check = False

    def visit_Slice(self, node: ast.Slice):
        if isinstance(self.nodeo, ast.Slice):
            tmp = self.nodeo
            if node.lower != None:
                self.nodeo = tmp.lower
                self.visit(node.lower)
            if node.upper != None:
                self.nodeo = tmp.upper
                self.visit(node.upper)
            if node.step != None:
                self.nodeo = tmp.step
                self.visit(node.step)

        else:
            self.check = False


# Only care for Call nodes
def MatchName(nodeo, coden, ParentO, ParentN, mappings, HAS_DEC, HAS_CB, libo, libn):
    # For Finding Class Base (Usually, base matches with base so there's a priority)
    for noden in ast.walk(coden):
        if (
            isinstance(nodeo, ast.ClassDef)
            and isinstance(noden, ast.ClassDef)
            and HAS_CB
        ):
            if nodeo.name == noden.name:
                return (noden, "classbase")

        if (
            (
                isinstance(nodeo, ast.FunctionDef)
                or isinstance(nodeo, ast.AsyncFunctionDef)
                or isinstance(nodeo, ast.ClassDef)
            )
            and (
                isinstance(noden, ast.FunctionDef)
                or isinstance(nodeo, ast.AsyncFunctionDef)
                or isinstance(noden, ast.ClassDef)
            )
            and HAS_DEC
        ):
            # Find Decorator based on function name
            if nodeo.name == noden.name:
                return (noden, "decorator")

    tmp_except = None
    tmp_except_score = 0
    EAC = ExtractArgs(only_args=False)
    EAC.visit(nodeo)
    argso = EAC.args

    # Finding Exception Handler
    if isinstance(nodeo, ast.ExceptHandler):
        for node in ast.walk(coden):
            if isinstance(node, ast.ExceptHandler):
                EAC = ExtractArgs(only_args=False)
                EAC.visit(node)
                argsn = EAC.args

                FCO = call.FindFCParent(ParentO, nodeo)
                FCN = call.FindFCParent(ParentN, node)

                FCNN = slicing.extract_name(FCN)
                FCNO = slicing.extract_name(FCO)

                score = len(argsn & argso)
                if FCNO == FCNN:
                    score += 1

                if score > tmp_except_score:
                    tmp_except = node
                    tmp_except_score = score
        return tmp_except, "except"

    # Extracting Arguments from original node
    EAC = ExtractArgs(only_args=True)
    EAC.visit(nodeo)
    argso = EAC.args

    if len(argso) == 0:
        # Should look for with more strict...
        tmp_node = None
        score = 0

        # More Extended Version
        tmp_nodeo = call.FindRealParent(ParentO, nodeo, depth=1)
        if isinstance(
            tmp_nodeo,
            (
                ast.For,
                ast.If,
                ast.While,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.AsyncFor,
                ast.With,
                ast.AsyncWith,
                ast.Try,
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            pass

        elif tmp_nodeo == None:
            tmp_nodeo = call.FindParent(ParentO, nodeo)
            nodeo = tmp_nodeo

        else:
            nodeo = tmp_nodeo

        exception_name = set()  # divided var

        EAC = ExtractArgs(only_args=False)
        EAC.visit(nodeo)
        argso = EAC.args

        for noden in ast.walk(coden):
            if type(nodeo) == type(noden):
                EAC = ExtractArgs(only_args=True)
                EAC.visit(noden)
                argsn = EAC.args

                if len(argsn) == 0:
                    FCO = call.FindFCParent(ParentO, nodeo)
                    FCN = call.FindFCParent(ParentN, noden)

                    FCNN = slicing.extract_name(FCN)
                    FCNO = slicing.extract_name(FCO)

                    if FCNO == FCNN:
                        tmp_score = 1

                    else:
                        tmp_score = 0

                    EAC = ExtractArgs(only_args=False)
                    EAC.visit(noden)
                    argsn = EAC.args

                    if libname(libo) in argso and libname(libn) in argsn:
                        tmp_score += 1

                    tmp_score += len(argsn & argso)

                    if tmp_score > score:
                        tmp_node = noden
                        score = tmp_score

                        # Divided Variable

                        if (
                            isinstance(noden, ast.Assign)
                            and len(noden.targets) == 1
                            and isinstance(noden.targets[0], ast.Name)
                        ):
                            exception_name.add(noden.targets[0].id)

                    else:
                        if exception_name & argsn and not isinstance(
                            noden,
                            (
                                ast.For,
                                ast.If,
                                ast.While,
                                ast.FunctionDef,
                                ast.AsyncFunctionDef,
                                ast.ClassDef,
                                ast.AsyncFor,
                                ast.With,
                                ast.AsyncWith,
                                ast.Try,
                                ast.Import,
                                ast.ImportFrom,
                            ),
                        ):
                            tmp_node = call.FindRealParent(ParentN, noden, depth=1)
                            if isinstance(
                                noden,
                                (
                                    ast.For,
                                    ast.If,
                                    ast.While,
                                    ast.FunctionDef,
                                    ast.AsyncFunctionDef,
                                    ast.ClassDef,
                                    ast.AsyncFor,
                                    ast.With,
                                    ast.AsyncWith,
                                    ast.Try,
                                    ast.Import,
                                    ast.ImportFrom,
                                ),
                            ):
                                tmp_node = noden

            else:
                EAC = ExtractArgs(only_args=False)
                EAC.visit(noden)
                argsn = EAC.args

                if exception_name & argsn:
                    tmp_node = call.FindRealParent(ParentN, noden, depth=1)

                    if isinstance(
                        noden,
                        (
                            ast.For,
                            ast.If,
                            ast.While,
                            ast.FunctionDef,
                            ast.AsyncFunctionDef,
                            ast.ClassDef,
                            ast.AsyncFor,
                            ast.With,
                            ast.AsyncWith,
                            ast.Try,
                            ast.Import,
                            ast.ImportFrom,
                        ),
                    ):
                        tmp_node = noden

        return (tmp_node, "no_args")

    tmp_node = None
    score = 0
    dvars = set()

    # Iterating through the nodes
    for noden in ast.walk(coden):
        tmp_score = 0
        if isinstance(noden, ast.Call):
            # Score initialization

            # 1. Find the arguments
            EAC = ExtractArgs()
            EAC.visit(noden)
            argsn = EAC.args

            if len(argsn) == 0:
                continue

            # 2. Considering the change of Var History
            for (var, FCname), val in mappings.items():
                NFCP = call.FindFCParent(ParentN, noden)
                nameN = slicing.extract_name(NFCP)
                cond1 = FCname == nameN and var not in val

                if var in argso and cond1:
                    # If the variable name is changed
                    for new_var in val:
                        if new_var in argsn:
                            argsn.remove(new_var)
                            argsn.add(var)

            # 3. Comparing the arguments
            tmp_score += len(argsn & argso)

            # 4. FC Parent Name
            FCO = call.FindFCParent(ParentO, nodeo)
            FCN = call.FindFCParent(ParentN, noden)

            FCNN = slicing.extract_name(FCN)
            FCNO = slicing.extract_name(FCO)

            if FCNO == FCNN:
                tmp_score += 1

            # Divided Variables
            """
            NODEO:
            dom = pyquery.PyQuery(STATION_DATA_URL.format(id))

            NEW CODE:
            url = STATION_DATA_URL.format(id)
            soup = BeautifulSoup(requests.get(url).text, "html.parser")

            In this case, original node should match with second line, even though overlapping variables exist
            """

            parent = call.FindRealParent(ParentN, noden, depth=1)
            if (
                isinstance(parent, ast.Assign)
                and ast.unparse(parent.value) == ast.unparse(noden)
                and len(argso & dvars) == 0
                and len(argso & argsn) > 0
            ):
                tmp_score = 0

                if isinstance(parent.targets[0], ast.Name):
                    argso.add(parent.targets[0].id)
                    dvars.add(parent.targets[0].id)

            # 6. Comparing the score
            if tmp_score >= score:
                tmp_node = noden
                score = tmp_score

        elif isinstance(noden, ast.Compare):
            # 1. Find the arguments
            EAC = ExtractArgs()
            EAC.visit(noden)
            argsn = EAC.args

            # 2. Considering the change of Var History
            for (var, FCname), val in mappings.items():
                NFCP = call.FindFCParent(ParentN, noden)
                nameN = slicing.extract_name(NFCP)
                cond1 = FCname == nameN and var not in val

                if var in argso and cond1:
                    # If the variable name is changed
                    for new_var in val:
                        if new_var in argsn:
                            argsn.remove(new_var)
                            argsn.add(var)

            # 3. Comparing the arguments
            tmp_score += len(argsn & argso)

            # 4. FC Parent Name
            FCO = call.FindFCParent(ParentO, nodeo)
            FCN = call.FindFCParent(ParentN, noden)

            FCNN = slicing.extract_name(FCN)
            FCNO = slicing.extract_name(FCO)

            if FCNO == FCNN:
                tmp_score += 1

            # 6. Comparing the score
            if tmp_score >= score:
                tmp_node = noden
                score = tmp_score

        elif isinstance(noden, ast.BinOp):
            # 1. Find the arguments
            EAC = ExtractArgs()
            EAC.visit(noden)
            argsn = EAC.args

            # 2. Considering the change of Var History
            for (var, FCname), val in mappings.items():
                NFCP = call.FindFCParent(ParentN, noden)
                nameN = slicing.extract_name(NFCP)
                cond1 = FCname == nameN and var not in val

                if var in argso and cond1:
                    # If the variable name is changed
                    for new_var in val:
                        if new_var in argsn:
                            argsn.remove(new_var)
                            argsn.add(var)

            # 3. Comparing the arguments
            tmp_score += len(argsn & argso)

            # 4. FC Parent Name
            FCO = call.FindFCParent(ParentO, nodeo)
            FCN = call.FindFCParent(ParentN, noden)

            FCNN = slicing.extract_name(FCN)
            FCNO = slicing.extract_name(FCO)

            if FCNO == FCNN:
                tmp_score += 1

            # 6. Comparing the score
            if tmp_score >= score:
                tmp_node = noden
                score = tmp_score

        # qwen 238때문에 했는데 얘 때문에sid eeffect 생기는거면 지워라
        elif type(nodeo) == type(noden):
            # 1. Find the arguments
            EAC = ExtractArgs()
            EAC.visit(noden)
            argsn = EAC.args

            # 2. Considering the change of Var History
            for (var, FCname), val in mappings.items():
                NFCP = call.FindFCParent(ParentN, noden)
                nameN = slicing.extract_name(NFCP)
                cond1 = FCname == nameN and var not in val

                if var in argso and cond1:
                    # If the variable name is changed
                    for new_var in val:
                        if new_var in argsn:
                            argsn.remove(new_var)
                            argsn.add(var)

            # 3. Comparing the arsguments
            tmp_score += len(argsn & argso)

            # 4. FC Parent Name
            FCO = call.FindFCParent(ParentO, nodeo)
            FCN = call.FindFCParent(ParentN, noden)

            FCNN = slicing.extract_name(FCN)
            FCNO = slicing.extract_name(FCO)

            if FCNO == FCNN:
                tmp_score += 1

            # 6. Comparing the score
            if tmp_score >= score:
                tmp_node = noden
                score = tmp_score

    tmp_node_real = call.FindRealParent(ParentN, tmp_node, depth=1)

    if isinstance(
        tmp_node_real,
        (
            ast.For,
            ast.If,
            ast.While,
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.AsyncFor,
            ast.With,
            ast.AsyncWith,
            ast.Try,
            ast.Import,
            ast.ImportFrom,
        ),
    ):
        tmp_node_real = tmp_node

    return (tmp_node_real, "call_node")


class ExtractArgs(ast.NodeVisitor):
    def __init__(self, only_args=False):
        self.args = set()
        self.only_args = only_args

    def visit_arg(self, node):
        if not self.only_args:
            self.args.add(node.arg)
            if node.annotation != None:
                self.args.add(ast.unparse(node.annotation))

    def visit_AnnAssign(self, node):
        if node.annotation != None:
            self.args.add(ast.unparse(node.annotation))

        if node.value != None:
            self.visit(node.value)

    def visit_Name(self, node):
        if isinstance(node, ast.Name) and not self.only_args:
            self.args.add(node.id)

    def visit_Constant(self, node):
        if isinstance(node, ast.Constant) and not self.only_args:
            if isinstance(node.value, str):
                self.args.add("constant_" + node.value)
            else:
                self.args.add(node.value)

    def visit_Call(self, node):
        tmp = self.only_args

        self.visit(node.func)

        self.only_args = False

        for arg in node.args:
            self.visit(arg)

        for kwarg in node.keywords:
            if isinstance(kwarg, ast.keyword):
                self.visit(kwarg.value)

        self.only_args = tmp


# Between cand_nodes, match the pair of nodes
def MatchSim(
    listo: list[ast.AST], listn: list[ast.AST], apio, ParentO, ParentN, typ=None
) -> dict:
    infoO = (
        dict()
    )  # key: nodeo / value : (vars, node parent stmt type, node grandparent stmt type)
    infoN = dict()
    result = dict()  # key: nodeo / value: noden

    # For Class Base Node
    if typ == "classbase":
        for nodeo in listo:
            for noden in listn:
                if (
                    isinstance(nodeo, ast.ClassDef)
                    and isinstance(noden, ast.ClassDef)
                    and nodeo.name == noden.name
                ):
                    result[nodeo] = noden
                    break

    # Organizing the information
    for nodeo in listo:
        NEO = call.NameExtractor()
        NEO.visit(nodeo)
        VarsO = NEO.list + NEO.constants + NEO.types
        infoO[nodeo] = (VarsO, nodeo, call.FindRealParent(ParentO, nodeo, 2))

    for noden in listn:
        NEN = call.NameExtractor()
        NEN.visit(noden)
        VarsN = NEN.list + NEN.constants + NEN.types
        infoN[noden] = (VarsN, noden, call.FindRealParent(ParentN, noden, 2))

    # Matching
    for nodeo, (VarsO, parento, grandparento) in infoO.items():
        tmpscore = (
            dict()
        )  # key: noden / value: (var num in common, node parent stmt type match boolean, node grandparent stmt type match boolean), If the parent or grandparent node is functin => record the name of it | None

        # record the matching score in tmpscore
        for noden, (VarsN, parentn, grandparentn) in infoN.items():
            score = len(set(VarsO) & set(VarsN))
            b1 = Stmtyp(type(parento), type(parentn))
            b2 = Stmtyp(type(grandparento), type(grandparentn))

            # b3
            cond = (type(parento) in {ast.FunctionDef, ast.AsyncFunctionDef}) and (
                type(parentn) in {ast.FunctionDef, ast.AsyncFunctionDef}
            )
            if cond and (parento.name == parentn.name):
                b3 = True
            elif cond:
                b3 = False
            else:
                b3 = None

            tmpscore[noden] = (score, b1, b2, b3)

        # Based on tmpscore, find the best matching node
        if len(tmpscore) != 0:
            _, bestnode = BestMap(apio, nodeo, tmpscore, ParentO, ParentN)
            result[nodeo] = bestnode

    return result


# Based on tmpscore, find the best matching node
def BestMap(apio, nodeo, tmpscore: dict[ast.AST : tuple], ParentO, ParentN):
    maxscore = -1
    bestnode = None

    for key, val in tmpscore.items():
        if val[0] > maxscore and Stmtyp(type(nodeo), type(key)):
            maxscore = val[0]
            bestnode = key

    # If two nodes have different stmt types -> replace the template with expr level
    if not Stmtyp(type(nodeo), type(bestnode)):
        # nodeo 모양도 바꿔야 되고 bestnode도 바꿔야 되고
        # nodeo = call.FindExprParent(ParentO, FindNameNode(nodeo, apio))
        # bestnode = call.FindExprParent(ParentN, FindNameNode(bestnode))
        print("not supported yet")

    return nodeo, bestnode


def ModDefVars(nodeo: ast.stmt, noden: ast.stmt, mapping, imps, ParentO, stack: set):
    FCP = call.FindFCParent(ParentO, nodeo)
    name = slicing.extract_name(FCP)

    # assign의 target만 고려하고, target이 여러개인 경우는 고려하지 않음
    if isinstance(nodeo, ast.Assign) and isinstance(noden, ast.Assign):
        DUGO = DefUseGraph(imps)
        DUGO.visit(nodeo)

        DUGN = DefUseGraph(imps)
        DUGN.visit(noden)

        OG1 = DUGO.graph
        NG1 = DUGN.graph

        if OG1[0]["def"] == NG1[0]["def"]:
            pass  # Don't need to.. change anything

        # Assume that only one target variable is assigned =>> For changinig targets
        elif (
            (len(OG1[0]["def"]) == len(NG1[0]["def"]))
            and len(OG1[0]["def"]) == 1
            and (OG1[0]["def"] != NG1[0]["def"])
        ):
            defo = OG1[0]["def"].pop()
            defn = NG1[0]["def"].pop()
            # 어차피 앞에서 다 함
            # if defo != defn:
            #     try:
            #         mapping[(defo, name)].add(defn)
            #     except:
            #         mapping[(defo, name)] = {defn}
            noden.targets = nodeo.targets

        # elif len(OG1[0]['def']) == 1:

        # In this case, Use new code's variable

        # Should be changed!!!!!!!!

        elif (len(OG1[0]["def"]) > 1) and len(
            NG1[0]["def"]
        ) == 1:  # 39.json (resp, data -> response ) | stdin, stdout, stderr -> result
            defos = list(OG1[0]["def"])
            defn = NG1[0]["def"].pop()

            if isinstance(nodeo.targets[0], ast.Tuple):
                defo = nodeo.targets[0].elts[0]

            try:
                mapping[(defo.id, name)].add(defn)
            except:
                mapping[(defo.id, name)] = {defn}

            noden.targets = [ast.Name(id=defo.id, ctx=ast.Store())]

        else:
            noden.targets = nodeo.targets

    elif isinstance(nodeo, ast.AnnAssign) and isinstance(noden, ast.AnnAssign):
        if noden in stack:
            nodeo.annotation = noden.annotation
            nodeo.value = noden.value
            return (mapping, nodeo, stack)

        else:
            stack.add(noden)
            noden.target = nodeo.target

    elif isinstance(nodeo, ast.Assign) and isinstance(noden, (ast.AsyncWith, ast.With)):
        # Assume one

        try:
            defo = nodeo.targets[0].id
        except:
            defo = ast.unparse(nodeo.targets[0])
        defn = noden.items[0].optional_vars.id

        try:
            mapping[(defo, name)].add(defn)
        except:
            mapping[(defo, name)] = {defn}

        noden.items[0].optional_vars = nodeo.targets[0]

    return mapping, noden, stack


class ModUseVars(ast.NodeTransformer):
    def __init__(self, mapping, funcdefs, ParentO, name_of_nodeo=None):
        self.mapping = mapping  # key: old val: set of new val
        self.funcdefs = funcdefs
        self.ParentO = ParentO
        self.name_of_nodeo = name_of_nodeo

    # def visit_Constant(self, node):
    #     FCP = call.FindFCParent(self.ParentO, node)
    #     name = context_remover_refactor.extract_name(FCP)

    #     for (var0, name0), val in self.mapping.items():  # old var, scope name | new var
    #         if node in val and name == name0:
    #             newnode = ast.Name(id=var0, ctx=ast.Load())
    #             return ast.copy_location(newnode, node)

    #     return node

    def visit_Name(self, node: ast.Name):
        FCP = call.FindFCParent(self.ParentO, node)
        name = slicing.extract_name(FCP)

        for (var0, name0), val in self.mapping.items():  # old var, scope name | new var
            if self.name_of_nodeo != None:
                if node.id in val and name0 == self.name_of_nodeo:
                    node.id = var0
            else:
                if node.id in val and name == name0:
                    node.id = var0

        return node

    def visit_Attribute(self, node: ast.Attribute):
        FCP = call.FindFCParent(self.ParentO, node)
        name = slicing.extract_name(FCP)

        for (var0, name0), val in self.mapping.items():  # var0: old val: new
            if self.name_of_nodeo == None:
                if (
                    (ast.unparse(node) in val)
                    and (name == name0)
                    and ("self" in ast.unparse(node))
                ):

                    tmp = ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=var0.split(".")[1],
                        ctx=node.ctx,
                    )
                    return tmp
            else:
                if (
                    (ast.unparse(node) in val)
                    and (name0 == self.name_of_nodeo)
                    and ("self" in ast.unparse(node))
                ):
                    tmp = ast.Attribute(
                        value=ast.Name(id="self", ctx=ast.Load()),
                        attr=var0.split(".")[1],
                        ctx=node.ctx,
                    )
                    return tmp

        node.value = self.visit(node.value)

        return node

    def visit_AnnAssign(self, node: ast.AnnAssign):
        return node

    def visit_Assign(self, node: ast.Assign):
        new = self.visit(node.value)
        node.value = new
        return node

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in self.funcdefs:
            for arg in range(len(node.args)):
                node.args[arg] = self.visit(
                    node.args[arg]
                )  # Do not change func (variable cannot be a func)
        else:
            node = self.generic_visit(node)

        return node


class DefUseGraph(ast.NodeVisitor):
    def __init__(self, imps={}):
        self.graph: dict[str : set[int : dict[str : set[str]]]] = (
            dict()
        )  # str: 'def', 'use', 'live'
        self.current_id = 0
        self.mapping = dict()
        self.tmp = set()  # for live variables
        self.imps = imps

    def visit_Module(self, node: ast.Module):
        for stmt in node.body:
            self.mapping[stmt] = self.current_id
            self.visit(stmt)
            self.current_id += 1

    def visit_FunctionDef(self, node: ast.FunctionDef):
        tmp = self.tmp  # for live vars

        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        self.graph[self.current_id]["def"].add(node.name)

        NE1 = synthesis.VarExtractor(node.name, check=True)
        NE1.visit(node.args)  # 다 할건지 아니면 node.args.args만 할건지
        self.tmp = self.tmp | set(NE1.vars[node.name])

        self.graph[self.current_id]["def"] = self.graph[self.current_id]["def"] | set(
            NE1.vars[node.name]
        )
        self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        self.tmp = tmp

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        tmp = self.tmp

        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        self.graph[self.current_id]["def"].add(node.name)

        NE1 = synthesis.VarExtractor(node.name, check=True)
        NE1.visit(node.args)  # 다 할건지 아니면 node.args.args만 할건지
        self.tmp = self.tmp | set(NE1.vars[node.name])

        self.graph[self.current_id]["def"] = self.graph[self.current_id]["def"] | set(
            NE1.vars[node.name]
        )
        self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        self.tmp = tmp

    def visit_ClassDef(self, node: ast.ClassDef):
        tmp = self.tmp

        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        self.graph[self.current_id]["def"].add(node.name)

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        self.tmp = tmp

    def visit_Return(self, node: ast.Return):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()

        if node.value != None:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(node.value)
            self.graph[self.current_id]["use"] = self.graph[self.current_id][
                "use"
            ] | set(NE1.vars["module"])

        self.graph[self.current_id]["live"] = self.tmp

    def visit_Delete(self, node: ast.Delete):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()

        for target in node.targets:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(target)
            self.graph[self.current_id]["use"] = self.graph[self.current_id][
                "use"
            ] | set(NE1.vars["module"])

        self.tmp = self.tmp - set(NE1.vars)
        self.graph[self.current_id]["live"] = self.tmp

    def visit_Assign(self, node: ast.Assign):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()

        for target in node.targets:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(target)
            self.graph[self.current_id]["def"] = self.graph[self.current_id][
                "def"
            ] | set(NE1.vars["module"])

        VarsN = synthesis.UnusedVars()
        VarsN.visit(node.value)

        self.tmp = self.tmp | set(NE1.vars)

        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            VarsN.used["module"]
        )
        self.graph[self.current_id]["live"] = self.tmp

    def visit_AugAssign(self, node: ast.AugAssign):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.target)
        self.graph[self.current_id]["def"] = self.graph[self.current_id]["def"] | set(
            NE1.vars["module"]
        )
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

        NE2 = synthesis.VarExtractor(check=True)
        NE2.visit(node.value)
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE2.vars["module"]
        )

        self.tmp = self.tmp | set(NE1.vars)
        self.graph[self.current_id]["live"] = self.tmp

    def visit_AnnAssign(self, node: ast.AnnAssign):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        if node.value != None:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(node.target)
            self.graph[self.current_id]["def"] = self.graph[self.current_id][
                "def"
            ] | set(NE1.vars["module"])

            NE2 = synthesis.VarExtractor(check=True)
            NE2.visit(node.value)
            self.graph[self.current_id]["use"] = self.graph[self.current_id][
                "use"
            ] | set(NE2.vars["module"])

            self.tmp = self.tmp | set(NE1.vars["module"])
            self.graph[self.current_id]["live"] = self.tmp

    def visit_For(self, node: ast.For):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.target)
        self.graph[self.current_id]["def"] = self.graph[self.current_id]["def"] | set(
            NE1.vars["module"]
        )

        self.tmp = self.tmp | set(NE1.vars["module"])
        self.graph[self.current_id]["live"] = self.tmp

        NE2 = synthesis.VarExtractor(check=True)
        NE2.visit(node.iter)
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE2.vars["module"]
        )

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for stmt in node.orelse:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

    def visit_AsyncFor(self, node: ast.AsyncFor):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.target)
        self.graph[self.current_id]["def"] = self.graph[self.current_id]["def"] | set(
            NE1.vars["module"]
        )

        self.tmp = self.tmp | set(NE1.vars["module"])
        self.graph[self.current_id]["live"] = self.tmp

        NE2 = synthesis.VarExtractor(check=True)
        NE2.visit(node.iter)
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE2.vars["module"]
        )

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for stmt in node.orelse:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

    def visit_While(self, node: ast.While):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.test)
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for stmt in node.orelse:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

    def visit_If(self, node: ast.If):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.test)
        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for stmt in node.orelse:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

    def visit_With(self, node: ast.With):
        tmp = self.tmp

        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        for item in node.items:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(item.context_expr)

            NE2 = synthesis.VarExtractor(check=True)
            if item.optional_vars != None:
                NE2.visit(item.optional_vars)
            self.tmp = self.tmp | set(NE1.vars["module"]) | set(NE2.vars["module"])

            self.graph[self.current_id]["use"] = self.graph[self.current_id][
                "use"
            ] | set(NE1.vars["module"])
            self.graph[self.current_id]["def"] = self.graph[self.current_id][
                "def"
            ] | set(NE2.vars["module"])
            self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        self.tmp = tmp

    def visit_AsyncWith(self, node: ast.AsyncWith):
        tmp = self.tmp

        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = set()

        for item in node.items:
            NE1 = synthesis.VarExtractor(check=True)
            NE1.visit(item.context_expr)

            NE2 = synthesis.VarExtractor(check=True)
            NE2.visit(item.optional_vars)

            self.tmp = self.tmp | set(NE1.vars["module"]) | set(NE2.vars["module"])

            self.graph[self.current_id]["use"] = self.graph[self.current_id][
                "use"
            ] | set(NE1.vars["module"])
            self.graph[self.current_id]["def"] = self.graph[self.current_id][
                "def"
            ] | set(NE2.vars["module"])
            self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        self.tmp = tmp

    # def visit_Match(self, node: Match) -> Any 안함

    def visit_Raise(self, node: ast.Raise):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node)

        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

    def visit_Try(self, node: ast.Try):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for handler in node.handlers:
            self.current_id += 1
            self.mapping[handler] = self.current_id
            self.visit(handler)

        for stmt in node.orelse:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

        for stmt in node.finalbody:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)

    def visit_Assert(self, node: ast.Assert):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node.test)

        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

    # def visit_Import  / def visit_ImportFrom -> assign var만 할거니까..
    # def visit_Global / def visit_Nonlocal

    def visit_Expr(self, node: ast.Expr):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        NE1 = synthesis.VarExtractor(check=True)
        NE1.visit(node)

        self.graph[self.current_id]["use"] = self.graph[self.current_id]["use"] | set(
            NE1.vars["module"]
        )

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self.graph[self.current_id] = dict()
        self.graph[self.current_id]["def"] = set()
        self.graph[self.current_id]["use"] = set()
        self.graph[self.current_id]["live"] = self.tmp

        for stmt in node.body:
            self.current_id += 1
            self.mapping[stmt] = self.current_id
            self.visit(stmt)
