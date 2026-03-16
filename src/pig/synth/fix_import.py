from pathlib import Path
import os

PIG_LIB_DIR = os.environ.get("PIG_LIB_DIR")

import ast, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from typing import Union

from mapping.gits import GIT_LOC

try:
    from . import llm_pre, call
except:
    import llm_pre, call


def is_total_import(root, var, libn) -> str:
    """Resolve the fully qualified import path of a variable within a library.

    Walks the AST to reconstruct the attribute access chain leading to
    ``var`` (e.g. ``torch.nn.Module`` → ``['torch', 'nn', 'Module']``),
    then verifies each component against the library's file system to
    determine how deep the chain corresponds to a real module path.

    :param root: The AST node to search for the variable reference.
    :type root: ast.AST
    :param var: The name of the variable or attribute whose import path
        is to be resolved.
    :type var: str
    :param libn: The name of the target library, used to look up the
        library's root path from ``GIT_LOC``.
    :type libn: str
    :return: The fully qualified dotted path of ``var`` up to the deepest
        resolvable module component (e.g. ``'torch.nn'``).
    :rtype: str
    """

    stack = []
    exception_node = set()
    # Do not visit arguments again!

    for node in ast.walk(root):
        if node in exception_node:
            continue

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id == var:
                    break
                else:
                    stack.append(node.func.id)
                    break

            for arg in node.args:
                exception_node.add(arg)
                for arg2 in ast.walk(arg):
                    exception_node.add(arg2)

            for keyword in node.keywords:
                exception_node.add(keyword)
                for keyword2 in ast.walk(keyword):
                    exception_node.add(keyword2)

        elif isinstance(node, ast.Attribute):
            if node.attr == var:
                break
            else:
                stack.append(node.attr)

        else:
            pass

    lib_path = PIG_LIB_DIR / (GIT_LOC[libn])
    dir_lib_path = lib_path
    file_lib_path = lib_path
    level = 0
    stack.reverse()

    for dir in stack:
        dir_lib_path = dir_lib_path / (dir)
        file_lib_path = file_lib_path / Path(dir + ".py")

        # compute level
        if dir_lib_path.exists():
            level += 1

        elif file_lib_path.exists():
            level += 1

        elif not dir_lib_path.exists():
            break

        elif not file_lib_path.exists():
            break

        else:
            pass

    new_var = ".".join([var] + stack[:level])
    return new_var


class extract_api_related_names(ast.NodeVisitor):
    """Extract all names referenced in an API-related expression.

    Visits an AST subtree and collects every :class:`ast.Name` identifier
    and :class:`ast.Attribute` name that appears within expressions
    involving ``apio``. For :class:`ast.Call` nodes, only arguments or the
    function itself that contain ``apio`` are traversed.

    :param apio: The old API name used to filter which call sub-expressions
        are visited.
    :type apio: str

    :ivar names: The set of collected name strings.
    :vartype names: set[str]
    """

    def __init__(self, apio):
        self.names = set()
        self.apio = apio

    def visit_Assign(self, node):
        self.visit(node.value)

    def visit_Name(self, node):
        self.names.add(node.id)

    def visit_Attribute(self, node):
        self.visit(node.value)
        self.names.add(node.attr)

    def visit_Call(self, node):
        if self.apio in ast.unparse(node.func):
            self.visit(node.func)

        else:
            for arg in node.args:
                if self.apio in ast.unparse(arg):
                    self.visit(arg)

            for keyword in node.keywords:
                if self.apio in ast.unparse(keyword):
                    self.visit(keyword)


def Importfind(
    code: ast.AST, nodes: set, var: str, libo: str, libn: str, apis, check=True
) -> tuple[set, set]:
    """Resolve and validate the import statement for a given variable name.

    Searches ``code`` for existing import statements that define ``var``,
    then verifies and corrects the import path against the actual library
    structure. If ``check`` is ``True``, the resolved import is validated
    and potentially rewritten to point to the correct new library path using
    :func:`is_total_import`, :func:`llm_pre.libname`, and
    :func:`ImportFindPath`. If ``check`` is ``False``, the existing import
    is returned as-is.

    :param code: The AST of the file being analysed, used to extract
        existing import statements.
    :type code: ast.AST
    :param nodes: The set of AST nodes where ``var`` is referenced, used
        to resolve the fully qualified import path via :func:`is_total_import`.
    :type nodes: set
    :param var: The variable name whose import statement is to be resolved.
    :type var: str
    :param libo: The name of the original library.
    :type libo: str
    :param libn: The name of the new library.
    :type libn: str
    :param apis: The API mapping passed through to :func:`ImportFindPath`
        for path resolution.
    :param check: If ``True``, validate and rewrite the import path to match
        the correct new library. If ``False``, return the existing import
        statement unchanged. Defaults to ``True``.
    :type check: bool
    :return: A tuple ``(import_nodes, resolved_vars)`` where ``import_nodes``
        is a set of corrected :class:`ast.Import` or :class:`ast.ImportFrom`
        nodes, and ``resolved_vars`` is the set of variable names that were
        successfully resolved.
    :rtype: tuple[set, set]
    """

    def get_imports_from_coden(code: ast.AST):
        result = dict()  # key: var name , value: ast.Import | ast.ImportFrom

        for node in ast.walk(code):
            if isinstance(node, ast.Import):
                for name in node.names:
                    if name.asname != None:
                        result[name.asname] = ast.Import(
                            names=[ast.alias(name=name.name, asname=name.asname)]
                        )

                    else:
                        result[name.name] = ast.Import(
                            names=[ast.alias(name=name.name, asname=None)]
                        )

            elif isinstance(node, ast.ImportFrom):
                for name in node.names:
                    if name.asname != None:
                        result[name.asname] = ast.ImportFrom(
                            module=node.module,
                            names=[ast.alias(name=name.name, asname=name.asname)],
                        )

                    else:
                        result[name.name] = ast.ImportFrom(
                            module=node.module,
                            names=[ast.alias(name=name.name, asname=None)],
                        )

            else:
                pass

        return result

    # Get the import statements from the code
    imports = get_imports_from_coden(code)
    result = set()
    vars = set()

    if var in imports.keys():
        cmp = imports[var]
        alias = cmp.names[0].asname
        if alias != None:
            new_var = alias

        else:
            # Check whether import path totally reflects
            try:
                _node = list(nodes)[0]
                new_var = is_total_import(_node, var, libn)

            except:
                new_var = var

    else:
        try:
            _node = list(nodes)[0]
            new_var = is_total_import(_node, var, libn)

        except:
            new_var = var

    # if check == True, checking the import path
    if check:
        # What if original llm import path is right? >> Return cmp
        cmp = None

        if new_var in imports.keys():
            cmp = imports[new_var]

            # wrongly import library name
            if isinstance(cmp, ast.ImportFrom):
                try:
                    lib_name = cmp.module.split(".")[0]
                except:
                    return (set(), {var})

            elif isinstance(cmp, ast.Import):
                lib_name = cmp.names[0].name.split(".")[0]

            import difflib

            if lib_name == libn and lib_name != llm_pre.libname(libn):
                if isinstance(cmp, ast.Import):
                    if len(cmp.names[0].name.split(".")) == 1:
                        new_imp = ast.Import(
                            names=[ast.alias(name=llm_pre.libname(libn), asname=libn)]
                        )
                        return ({new_imp}, {var})

                    else:
                        new_imp = ast.Import(
                            names=[
                                ast.alias(
                                    name=cmp.names[0].name.replace(
                                        libn, llm_pre.libname(libn)
                                    ),
                                    asname=cmp.names[0].asname,
                                )
                            ],
                        )

                        return ({new_imp}, {var})

                elif isinstance(cmp, ast.ImportFrom):
                    new_imp = ast.ImportFrom(
                        module=cmp.module.replace(libn, llm_pre.libname(libn)),
                        names=[
                            ast.alias(
                                name=cmp.names[0].name, asname=cmp.names[0].asname
                            )
                        ],
                    )

                    return ({new_imp}, {var})

            # Wrong lib match
            elif (
                difflib.SequenceMatcher(None, lib_name, libn).ratio() > 0.8
                and lib_name != llm_pre.libname(libn)
                and lib_name != libo
            ):
                # Similar library name
                if isinstance(cmp, ast.Import) and cmp.names[0].asname != None:
                    new_imp = ast.Import(
                        names=[
                            ast.alias(
                                name=llm_pre.libname(libn), asname=cmp.names[0].asname
                            )
                        ],
                    )

                    return ({new_imp}, {var})

                elif isinstance(cmp, ast.Import):
                    new_imp = ast.Import(
                        names=[ast.alias(name=llm_pre.libname(libn), asname=var)],
                    )

                    return ({new_imp}, {var})

                elif isinstance(cmp, ast.ImportFrom):
                    new_imp = ast.ImportFrom(
                        module=cmp.module.replace(libn, llm_pre.libname(libn)),
                        names=[
                            ast.alias(
                                name=cmp.names[0].name, asname=cmp.names[0].asname
                            )
                        ],
                    )

                    return ({new_imp}, {var})

            if llm_pre.libname(libn) not in ast.unparse(
                cmp
            ) and libn not in ast.unparse(cmp):
                if lib_name == libo:
                    cmp_str = (
                        ast.unparse(cmp).replace(
                            f" {libo}", f" {llm_pre.libname(libn)}"
                        )
                        + f" as {llm_pre.libname(libo)}"
                    )
                    cmp = ast.parse(cmp_str).body[0]

                else:
                    # Using other lib
                    return ({cmp}, {var})

            if check_available_import(cmp, libn) and llm_pre.libname(
                libn
            ) in ast.unparse(cmp):
                return ({cmp}, {var})
        # 38
        elif llm_pre.libname(libn) == new_var.split(".")[0] and new_var in ast.unparse(
            _node
        ):
            cmp = ast.Import(names=[ast.alias(name=new_var)])
            return ({cmp}, {var})

        NCImport = ImportFindPath(libo, libn, var, nodes, apis, cmp)

        if len(NCImport) > 0:
            vars.add(var)
            result = result | NCImport

    else:
        if var in imports.keys():
            result.add(imports[var])
            vars.add(var)

    return (result, vars)


# Getting unassigned variable and find the import path (This is because llm sometimes omits the import statement)
def ImportFindPath(libo: str, libn: str, v1: str, nodes, apis, cmp=None) -> set:
    """Resolve the correct import statement for a variable in the new library.

    Searches the new library's API map to find all candidate import paths for
    ``v1``, then validates each candidate against the actual usage pattern in
    ``nodes`` to determine the most appropriate import form. Duplicate
    candidates are resolved via :func:`duplicate_imports_resolve` or, as a
    last resort, by string similarity against ``cmp``.

    The resolution process is handled by three inner helpers:

    - ``find(v1)``: scans ``apis`` to collect all candidate paths where
      ``v1`` appears as a class, function, constant, or module name.
    - ``pmaker(cand_path)``: expands a single candidate into the set of
      concrete import forms it could take (e.g. ``import A.B`` and
      ``from A import B``).
    - ``check(nodes, cand_path)``: inspects how ``v1`` is actually used in
      each node and selects the import form whose path components match the
      usage pattern.

    :param libo: The name of the original library.
    :type libo: str
    :param libn: The name of the new library.
    :type libn: str
    :param v1: The variable name whose import statement is to be resolved.
    :type v1: str
    :param nodes: The set of AST nodes where ``v1`` is referenced, used to
        infer the correct import form from actual usage.
    :type nodes: set
    :param apis: The API map of the new library, structured as
        ``{module_path: (classes, _, functions, _, constants)}``.
    :param cmp: An optional existing import node from the LLM-generated code,
        used as a similarity reference when duplicate candidates remain after
        resolution. Defaults to ``None``.
    :type cmp: ast.Import | ast.ImportFrom | None
    :return: A set containing the resolved import node(s). Normally contains
        a single :class:`ast.Import` or :class:`ast.ImportFrom` node; may
        contain multiple if resolution is inconclusive.
    :rtype: set
    """

    def find(v1):
        cand_paths = set()
        for path, vals in apis.items():
            classes, _, functions, _, constants = vals

            for cand_c in classes:
                # class, function, constant
                if v1 == cand_c[0]:
                    cand_paths.add((ast.ImportFrom, path, cand_c[0]))

            for cand_f in functions:
                if v1 == cand_f[0]:
                    cand_paths.add((ast.ImportFrom, path, cand_f[0]))

            for cand_co in constants:
                if v1 == cand_co[0]:
                    cand_paths.add((ast.ImportFrom, path, cand_co[0]))

            if v1 == path.split(".")[-1]:
                cand_paths.add((ast.Import, path))
                if path.count(".") > 0:
                    # from A.B import C
                    try:
                        cand_paths.add(
                            (
                                ast.ImportFrom,
                                ".".join(path.split(".")[:-1]),
                                path.split(".")[-1],
                            )
                        )

                    except:
                        pass

        return cand_paths

    def pmaker(cand_path):
        paths = set()

        if cand_path[0] == ast.Import:
            # 1. full path 'import A.B.C'
            paths.add((cand_path[1], ast.Import))

            # 2. Partial Path 'from A.B import C'
            if "." in cand_path[1]:
                partials = cand_path[1].split(".")
                module = ".".join(partials[0 : len(partials) - 1])
                paths.add((module, cand_path[1].split(".")[-1], ast.ImportFrom))

        if cand_path[0] == ast.ImportFrom:
            # 3. Simplified Path 'from A.B import a'
            paths.add((cand_path[1], cand_path[2], ast.ImportFrom))
            paths.add((cand_path[1], ast.Import))

        return paths

    def check(nodes, cand_path) -> set:
        tmp = set()

        for node in nodes:
            if node == None:
                continue

            node_visitor = extract_api_related_names(v1)
            node_visitor.visit(node)
            api_related_names = node_visitor.names

            paths = pmaker(cand_path)

            for path in paths:
                typ = path[-1]

                if typ is ast.Import:
                    if path[0] in ast.unparse(node):
                        tmp.add(ast.Import(names=[ast.alias(name=path[0])]))

                elif typ is ast.ImportFrom:
                    path_stack = []

                    for _path in path[0].split(".") + [path[1]]:
                        if (_path) not in api_related_names:
                            path_stack.append(_path)

                        else:
                            cond0 = ("." + _path) in ast.unparse(node)  # .a
                            cond1 = (_path + ".") in ast.unparse(node)  # a.

                            if cond0 and cond1:  # .a.
                                path_stack.append(_path)

                            elif cond0 and not cond1:  # .a
                                if len(path_stack) == 1 and path_stack[
                                    0
                                ] + "." in ast.unparse(node):
                                    tmp.add(
                                        ast.Import(
                                            names=[
                                                ast.alias(
                                                    name=".".join([path_stack[0]])
                                                )
                                            ],
                                            level=0,
                                        )
                                    )

                                else:
                                    cond0 = path_stack[-1] in api_related_names
                                    cond1 = ("." + path_stack[-1]) not in ast.unparse(
                                        node
                                    )

                                    if cond0 and cond1:
                                        tmp.add(
                                            ast.ImportFrom(
                                                module=".".join(path_stack[:-1]),
                                                names=[ast.alias(name=path_stack[-1])],
                                                level=0,
                                            )
                                        )

                            elif not cond0 and cond1:  # a.

                                if _path == path[1] and (
                                    "." + path[1] not in ast.unparse(node)
                                ):
                                    tmp.add(
                                        ast.ImportFrom(
                                            module=".".join(path_stack),
                                            names=[ast.alias(name=_path)],
                                            level=0,
                                        )
                                    )

                                else:
                                    path_stack.append(_path)

                            else:
                                # 단독 사용
                                if _path == path[1] and (
                                    "." + path[1] not in ast.unparse(node)
                                ):
                                    tmp.add(
                                        ast.ImportFrom(
                                            module=".".join(path_stack),
                                            names=[ast.alias(name=_path)],
                                            level=0,
                                        )
                                    )

                                else:
                                    path_stack.append(_path)

        return tmp

    result = set()

    # LLM sometimes omits the import statement as using original lib name
    if llm_pre.libname(libo) == v1:
        result.add(
            ast.Import(
                names=[
                    ast.alias(
                        name=(llm_pre.libname(libn)), asname=llm_pre.libname(libo)
                    )
                ]
            )
        )

    cand_paths = find(v1)

    for cand_path in cand_paths:
        tmp_unparsed = {ast.unparse(r) for r in result}
        tmp_imps: set = check(nodes, cand_path)

        if len(tmp_imps) > 0:
            tmp_imp = tmp_imps.pop()
            if ast.unparse(tmp_imp) not in tmp_unparsed:
                result.add(tmp_imp)

    if len(result) > 1:
        result = duplicate_imports_resolve(result, nodes, libn, v1, cmp)

    # if really still duplicate?
    if len(result) > 1:
        print(
            "Warning: Still duplicate imports found after resolving duplicates.",
            result,
        )

        # Calculate similarity score

        if cmp == None:
            return result

        else:
            import difflib

            max_score = 0
            cmp_str = ast.unparse(cmp)

            if isinstance(cmp, ast.Import):
                cmp_str = cmp.names[0].name

            for r in result:
                r_imp_str = ast.unparse(r)

                if isinstance(r, ast.Import):
                    r_imp_str = r.names[0].name
                else:
                    r_imp_str = ""
                    if r.module != None:
                        r_imp_str = r.module + "." + r.names[0].name

                score = difflib.SequenceMatcher(None, cmp_str, r_imp_str).ratio()

                if score > max_score:
                    max_score = score
                    result = {r}

            return result

    return result


# Only get accessible APIs and arguments if needed from the path
def get_accessible_apis(_path: Path, libn: str, name=None, dir=False) -> dict:
    """Extract publicly accessible API names and their signatures from a library path.

    Parses the Python source file or directory at ``_path`` and collects all
    top-level classes, functions, annotated assignments, global variables, and
    re-exported names. If ``name`` is specified, only the entry matching that
    name is returned, with the source path appended for import resolution.

    The extraction is handled by three inner helpers:

    - ``get_apis(path, stack)``: recursively parses files and directories,
      populating the result dicts with discovered API entries.
    - ``get_func_args(node)``: extracts the full argument signature of a
      function, including positional, keyword-only, default, and variadic
      arguments.
    - ``get_class_args(node)``: extracts the ``__init__`` signature of a
      class, falling back to ``(0, …)`` if no ``__init__`` is present and
      no base classes exist, or ``('inf', …)`` if base classes are present.

    Each API entry is stored as a list of the form:
    ``[type, min_args, min_kwargs, max_args, max_kwargs, default_names,
    kw_names, ordinary_names]`` where ``type`` is one of ``'class'``,
    ``'func'``, or ``'var'``.

    :param _path: Path to the library source file (``.py``) or directory to
        inspect.
    :type _path: Path
    :param libn: The name of the library being inspected (reserved for future
        use).
    :type libn: str
    :param name: If provided, only the API entry matching this name is
        returned, with ``[path, 'imp']`` appended to its value.
    :type name: str | None
    :param dir: If ``True``, treat ``_path`` as a directory and enumerate its
        submodules instead of parsing a single file.
    :type dir: bool
    :return: A tuple ``(result, result2)`` where ``result`` maps each API name
        to its signature list, and ``result2`` maps names discovered in
        ``__init__.py`` (for directory paths) to their signatures.
    :rtype: tuple[dict, dict]
    """

    result = dict()  # normal
    # key: name, value: (typ, totalargument number, keyword argument number, keyword argument names)
    result2 = dict()

    def get_apis(path: Path, stack: set, name=None, dir=False):
        if dir:  # Directory
            for f in path.iterdir():
                if f.is_file():
                    result[str(f).split("/")[-1].split(".")[0]] = (
                        "module",
                        None,
                        None,
                        None,
                    )

            if (path / Path("__init__.py")).is_file():
                _result1, _ = get_apis(path / Path("__init__.py"), stack)
                result2.update(_result1)

        else:  # File
            with open(path, "r") as f:
                code = f.read().strip()

            target_result = result

            root = ast.parse(code)
            Parent = call.ParentAst(root)

            for stmt in root.body:
                if isinstance(stmt, ast.ClassDef):
                    if name == None:
                        target_result[stmt.name] = get_class_args(stmt)

                    else:
                        if stmt.name == name:
                            target_result[stmt.name] = get_class_args(stmt) + [
                                path,
                                "imp",
                            ]

                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if name == None:
                        target_result[stmt.name] = ["func"] + get_func_args(stmt)
                    else:
                        if stmt.name == name:
                            target_result[stmt.name] = (
                                ["func"]
                                + get_func_args(stmt)
                                # + [path, "imp"]
                            )

                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Name):
                        if name == None:
                            target_result[stmt.target.id] = ["var", 0, 0, []]
                        else:
                            if stmt.target.id == name:
                                target_result[stmt.target.id] = ["var", 0, 0, []] + [
                                    path,
                                    "imp",
                                ]
                else:
                    pass

            # 이건 depth 상관없이 가능
            for node in ast.walk(root):
                if isinstance(node, ast.Global):
                    for _name in node.names:
                        if name == None:
                            target_result[_name] = ["var", 0, 0, []]
                        else:
                            if _name == name:
                                target_result[_name] = ["var", 0, 0, []] + [path, "imp"]

                if isinstance(node, ast.Assign):
                    if call.FindFCParent(Parent, node) == None:
                        for target in node.targets:
                            if name == None:
                                if isinstance(target, ast.Name):
                                    target_result[target.id] = ["var", 0, 0, []]

                            else:
                                if isinstance(target, ast.Name) and target.id == name:
                                    target_result[target.id] = ["var", 0, 0, []] + [
                                        path,
                                        "imp",
                                    ]

                if isinstance(node, ast.ImportFrom):
                    for _alias in node.names:
                        if name == None:
                            if _alias.asname == None:
                                target_result[_alias.name] = ["var", 0, 0, []]
                            else:
                                target_result[_alias.asname] = ["var", 0, 0, []]

                        else:
                            if _alias.name == name:
                                target_result[_alias.name] = ["var", 0, 0, []] + [
                                    path,
                                    "imp",
                                ]

        return result, result2

    # Get all arguments of Function as a form of (total argument num, keyword argument num, maximum arglen, maximum kw_len, kw_lst)
    def get_func_args(node: Union[ast.FunctionDef, ast.AsyncFunctionDef], cls=False):
        args = node.args
        kw_lst = []  # name

        # minimum num of arguments that should be filled
        default_len = len(args.defaults)
        arg_len = len(args.args) - default_len
        kw_len = args.kw_defaults.count(None)

        # Exception for self
        for i in range(len(args.args)):
            if cls and args.args[i].arg == "self":
                arg_len -= 1

        # maximum num of arguments that can be filled
        if args.vararg == None:
            max_arglen = len(args.args)
        else:
            max_arglen = "inf"

        if args.kwarg == None:
            max_kwlen = len(args.kwonlyargs)
        else:
            max_kwlen = "inf"

        # kwonlyargs' names
        for i in range(len(args.kwonlyargs)):
            default_value = args.kw_defaults[i]
            if default_value == None:
                kw_lst.append(args.kwonlyargs[i].arg)

        default_names = []

        # default names
        start = (len(args.posonlyargs) + len(args.args)) - len(args.defaults)
        target_args = args.posonlyargs + args.args

        for i in range(len(args.defaults)):
            new_index = start + i
            default_names.append(target_args[new_index].arg)

        ordinary_names = []

        # Ordinary argument name
        for i in range(len(args.args) - len(args.defaults)):
            ordinary_names.append(args.args[i].arg)

        # total argument number and keyword argument number and if kw!=inf, kw_lst stands for names of kwarg
        return [
            arg_len,
            kw_len,
            max_arglen,
            max_kwlen,
            default_names,
            kw_lst,
            ordinary_names,
        ]

    # Get all arguments of class of __init__
    def get_class_args(node: ast.ClassDef):
        for stmt in node.body:
            if (
                isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
                and stmt.name == "__init__"
            ):
                return ["class"] + get_func_args(stmt, True)

        # if there's no __init__ function... and no base

        if len(node.bases) == 0:
            return ["class", 0, 0, 0, 0, 0, [], []]

        else:
            return ["class", "inf", "inf", "inf", "inf", "inf", [], []]

    r1, r2 = get_apis(_path, set(), name=name, dir=dir)

    return r1, r2


def duplicate_imports_resolve(
    imps: set[ast.Import | ast.ImportFrom],
    nodes: set[ast.AST],
    libn: str,
    var: str,
    cmp=None,
):
    """Resolve a set of duplicate import candidates down to a single correct import.

    Given multiple candidate import statements for the same variable ``var``,
    inspects how ``var`` is actually used in ``nodes`` and cross-references
    each candidate against the new library's source files to determine which
    import is valid. Duplicates that survive the initial check are further
    resolved by module path depth or import type counts.

    The resolution process is handled by several inner helpers:

    - ``api_type()``: determines whether ``var`` is used as an
      :class:`ast.Attribute`, :class:`ast.Call`, or bare :class:`ast.Name`
      by tallying occurrences across ``nodes``.
    - ``find_next_attribute(nodes, var)``: identifies the most common
      attribute accessed on ``var`` (e.g. ``var.attr``), used when usage
      type is ``'Attribute'``.
    - ``find_args(node)``: extracts the positional and keyword argument
      counts from a :class:`ast.Call` node.
    - ``find_last_call(node)``: returns the final name or attribute in a
      call expression (e.g. ``c`` from ``a.b.c()``).
    - ``check(...)``: validates a single candidate import against the
      library's accessible APIs and the observed usage type, returning
      ``(True, import_node)`` if valid or ``(False, None)`` otherwise.

    :param imps: The set of candidate :class:`ast.Import` or
        :class:`ast.ImportFrom` nodes to resolve.
    :type imps: set[ast.Import | ast.ImportFrom]
    :param nodes: The AST nodes where ``var`` is referenced, used to infer
        usage type and argument signatures.
    :type nodes: set[ast.AST]
    :param libn: The name of the new library, used to locate its source
        files via ``GIT_LOC``.
    :type libn: str
    :param var: The variable name whose import is being resolved.
    :type var: str
    :param cmp: An optional existing import node from the LLM-generated
        code, used as a string-similarity reference if duplicates remain
        after all other resolution steps. Defaults to ``None``.
    :type cmp: ast.Import | ast.ImportFrom | None
    :return: A set containing a single resolved import node. May contain
        more than one entry if resolution is inconclusive.
    :rtype: set[ast.Import | ast.ImportFrom]
    """

    lib_path = PIG_LIB_DIR / Path(GIT_LOC[libn])
    typ_records = {"Attribute": 0, "Call": 0, "Name": 0}
    call_records = {
        "args": 0,
        "keywords": set(),
        "kw_args": 0,
    }  # for the case of call, record the arguments and keywords

    result = set()

    def check(
        node_typ,
        var,
        module_typ,
        arg_record,
        apis,
        imp_path,
        original_path: str,
        attr=None,
    ):

        # apis: key: name, value: (total argument num, keyword argument num, maximum arglen, maximum kw_len, kw_lst)
        def mod_path(
            info, index, imp_path: Union[ast.Import, ast.ImportFrom], original_path: str
        ):
            # if info[index][-1] == "imp":
            #     new_path: str = str(info[index][-2])  # /a/b/c
            #     paths = new_path.split("/" + original_path + "/")  # [/a/, /c]
            #     _new_path = (original_path + "/" + paths[1]).replace("/", ".")

            #     if ".py" in _new_path:
            #         new_path = _new_path[:-3]

            #     if ".pyi" in _new_path:
            #         new_path = _new_path[:-4]

            #     # Make it as a form of ImportFrom
            #     func = new_path.split(".")[-1]
            #     module = ".".join(new_path.split(".")[:-1])

            #     return ast.ImportFrom(
            #         module=module + "." + func, names=[ast.alias(name=index)], level=0
            #     )

            # else:
            return imp_path

        if node_typ == "Attribute":
            if module_typ == "module":
                # 뒤에 오는 attr가 파일에 있어야만 함
                if attr in apis.keys():
                    return (True, mod_path(apis, module, imp_path, original_path))

                else:
                    return (False, None)

            elif module_typ == "file":
                # 지금 주어진 var이 클래스인지 일반 변수인지 확인해야함
                if var in apis.keys():
                    if apis[var][0] == "func":
                        return (False, None)
                    elif apis[var][0] in ["class", "imp", "var"]:
                        # 추후에 클래스에서 접근가능한 메서드인지 확인 근데 이러면 걍
                        return (
                            True,
                            mod_path(apis, var, imp_path, original_path),
                        )  # 얘는 var를 import 하는거지 attr임포트하는거아님
                    else:
                        return (False, None)

                else:
                    return (False, None)

            else:
                return (False, None)

        elif node_typ == "Call":
            if var not in apis.keys():
                return (False, None)

            target = apis[var]

            if target[0] == "func" or target[0] == "class":
                # Check for argument numbers

                args_len = target[1]  # minimum
                kw_len = target[2]  # minimum
                max_arglen = target[3]
                max_kwlen = target[4]
                default_names = target[5]
                kw_names = target[6]
                ordinary_names = target[7]

                _kw_args_len = arg_record["kw_args"]
                _kw_args = []

                _default_args = []

                for kw in arg_record["keywords"]:
                    if kw in default_names:
                        _kw_args_len -= 1
                        _default_args.append(kw)

                        if kw in kw_names:
                            _kw_args.remove(kw)

                    if kw in ordinary_names:
                        _kw_args_len -= 1
                        arg_record["args"] += 1

                cond0 = (
                    (args_len == "inf")
                    or (args_len <= arg_record["args"])
                    and (kw_len <= (_kw_args_len))
                )  # minimum arg length?
                cond1 = (max_arglen == "inf") or (
                    max_arglen >= arg_record["args"]
                )  # maximum arg length?
                cond2 = (max_kwlen == "inf") or (
                    max_kwlen >= _kw_args_len
                )  # maximum kw length?
                cond3 = (max_kwlen == "inf") or set(_kw_args).issubset(
                    set(kw_names)
                )  # kw_args should be subset of kw_names
                cond4 = set(_default_args).issubset(set(default_names))
                cond = cond0 and cond1 and cond2 and cond3 and cond4

                if cond:
                    return (True, mod_path(apis, var, imp_path, original_path))
                else:
                    return (False, None)

            elif target[0] in ["imp", "var"]:
                # We don't know...
                return (True, mod_path(apis, var, imp_path, original_path))

            else:
                print("Error: Unknown type", target[0], target)
                # etc
                return (False, None)

        else:  # Name
            if module_typ == "module":
                return (False, None)
            elif module_typ == "file" and var in apis.keys():
                # 이건 모르니까 그냥 True로 놔둠
                return (True, mod_path(apis, var, imp_path, original_path))
            else:
                return (False, None)

    def find_next_attribute(nodes: ast.AST, var: str) -> str:
        cands = []

        for node in nodes:
            code = ast.unparse(node)
            std = var + "."
            attrs = None  # Default

            if std in code:
                attrs = (code.split(std)[1]).split(".")[0]

            cands.append(attrs)

        # Pick Most count among cands
        attr = max(cands, key=cands.count)

        return attr

    def find_args(node: ast.Call) -> tuple[int, list[str]]:
        # [arg_len, kw_len, max_arglen, max_kwlen, kw_lst]
        lst = []

        for keyword in node.keywords:
            if keyword.arg != None:
                lst.append(keyword.arg)

        return (len(node.args), len(node.keywords), lst)

    # a.b.c() -> c | a.b.c.d() -> d
    def find_last_call(node: ast.Call) -> str:
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        else:
            print("Error: Unknown type")
            return None

    def api_type():
        # 1. Check how imported api is used (Attribute, Call, or Name)
        for node in nodes:
            for n in ast.walk(node):
                if isinstance(n, ast.Attribute):
                    if n.attr == var:
                        print("plz check this case")

                    if isinstance(n.value, ast.Name) and n.value.id == var:
                        typ_records["Attribute"] += 1
                        break

                if isinstance(n, ast.Call) and (find_last_call(n)) == var:
                    typ_records["Call"] += 1
                    args_len, kw_len, kw_lst = find_args(n)

                    if call_records["args"] < args_len:
                        call_records["args"] = args_len

                    if call_records["kw_args"] < kw_len:
                        call_records["kw_args"] = kw_len

                    call_records["keywords"] = call_records["keywords"] | set(kw_lst)

                    break

                if isinstance(n, ast.Name) and n.id == var:
                    typ_records["Name"] += 1

        # Pick highest count
        typ = max(typ_records, key=typ_records.get)

        return typ

    # 2. Extract all accessible APIs from the path
    info = dict()

    for imp in imps:

        if isinstance(imp, ast.Import):
            if imp.names[0].name.count(".") == 0:
                module = ""
            else:
                index = imp.names[0].name.index(".")
                module = imp.names[0].name[index + 1 :]

            module = module.replace(".", "/")

            # File or Module
            b1 = Path(lib_path / Path(module + ".py")).exists()
            b2 = Path(lib_path / Path(module + ".pyi")).exists()
            # b3 = path.isfile(lib_path / Path(imp.names[0].name + '.pyx')) Cython File not supported yet
            b4 = Path(lib_path / Path(module)).exists()

            if b1:
                # dot_path = imp.names[0].name.replace(".", "/")  # a.b.c -> a/b/c
                apis1, _ = get_accessible_apis(
                    lib_path / Path(module + ".py"), libn
                )  # dot_path went to module
                info[imp] = ("file", apis1)

            elif b2:
                dot_path = imp.names[0].name.replace(".", "/")  # a.b.c -> a/b/c
                apis1, _ = get_accessible_apis(lib_path / Path(dot_path + ".pyi"), libn)
                info[imp] = ("file", apis1)

            elif b4:
                dot_path = module.replace(".", "/")
                apis1, apis2 = get_accessible_apis(
                    lib_path / Path(dot_path), libn, dir=True
                )
                #### Error
                info[imp] = ("module_file", apis1, apis2)

            else:
                info[imp] = ("None", dict())

        elif isinstance(imp, ast.ImportFrom):
            if imp.module.count(".") == 0:
                module = ""
            else:
                index = imp.module.index(".")
                module = imp.module[index + 1 :]

            module = module.replace(".", "/")  # module (directory)

            for _alias in imp.names:
                cond0 = _alias.name == "*"

                b1 = Path(lib_path / Path(module) / Path("__init__.py")).exists()
                b2 = Path(lib_path / Path(module + ".py")).exists()  # name is api
                b3 = Path(lib_path / Path(module + ".pyi")).exists()  # name is api
                b4 = Path(
                    lib_path / Path(module + _alias.name)
                ).exists() and os.path.isdir(
                    (Path(lib_path / Path(module + _alias.name)))
                )
                # b4 = path.isfile(lib_path / Path(module + '.pyx')) Cython File not supported yet

                if b4:
                    apis1, apis2 = get_accessible_apis(
                        lib_path / Path(module + _alias.name), libn, dir=True
                    )
                    if var in apis1.keys():
                        info[imp] = ("module", apis1)
                    elif var in apis2.keys():
                        info[imp] = ("file", apis2)
                    else:
                        info[imp] = ("None", dict())

                elif b2:
                    if cond0:
                        # Import all APIS in
                        apis1, _ = get_accessible_apis(
                            lib_path / Path(module + ".py"), libn
                        )

                    else:
                        # Import specific API
                        apis1, _ = get_accessible_apis(
                            lib_path / Path(module + ".py"), libn, name=_alias.name
                        )

                    info[imp] = ("file", apis1)

                elif b3:
                    if cond0:
                        # Import all APIs
                        apis1, _ = get_accessible_apis(
                            lib_path / Path(module + ".pyi"), libn
                        )

                    else:
                        # Import specific API
                        apis1, _ = get_accessible_apis(
                            lib_path / Path(module + ".pyi"), libn, name=_alias.name
                        )

                    info[imp] = ("file", apis1)

                elif b1:
                    apis1, apis2 = get_accessible_apis(
                        Path(lib_path / Path(module) / Path("__init__.py")), libn
                    )

                    if var in apis1.keys():
                        info[imp] = ("file", apis1)

                    else:
                        info[imp] = ("None", dict())

                else:
                    info[imp] = ("None", dict())

    typ = api_type()

    # Iterate over
    for imp in imps:
        if isinstance(imp, ast.ImportFrom):
            if typ == "Attribute":
                attr = find_next_attribute(nodes, var)

            else:
                attr = None

            lib_name_path = str(lib_path).split("/")[-1]

            (b0, new_path) = check(
                typ,
                var,
                info[imp][0],
                call_records,
                info[imp][1],
                imp,
                lib_name_path,
                attr=attr,
            )

            if b0:
                result.add(new_path)

        else:
            result.add(imp)

    # Check for unparsed imports
    history = set()
    real_result = set()

    for i in result:
        if ast.unparse(i) not in history:
            real_result.add(i)
            history.add(ast.unparse(i))

    if len(real_result) > 1:
        # If there are still duplicate imports, work for deeper depth
        try:
            real_result = sorted(
                list(real_result), key=lambda x: x.module.count("."), reverse=True
            )
            real_result = {real_result[0]}

        except:
            imp_cnt = 0
            fimp_cnt = 0

            for i in real_result:
                if isinstance(i, ast.Import):
                    imp_cnt += 1
                else:
                    fimp_cnt += 1

            if imp_cnt == fimp_cnt:
                real_result = {list(real_result)[0]}

            else:
                print("Error: Unknown Error", real_result)

    else:
        pass
        # print("No duplicate imports!")

    return real_result


# Checking whether import path is available or not
def check_available_import(import_node: Union[ast.Import, ast.ImportFrom], libn):
    """Check whether an import node resolves to a real path in the library source.

    Converts the dotted module path of ``import_node`` into a file system path
    and verifies that it exists within the library's source tree. For
    :class:`ast.ImportFrom` nodes, additionally checks that the imported name
    is actually accessible at that path via :func:`get_accessible_apis`.

    Import nodes that do not reference ``libn`` at all are considered valid
    and return ``True`` immediately.

    :param import_node: The import statement to validate.
    :type import_node: Union[ast.Import, ast.ImportFrom]
    :param libn: The name of the new library, used to locate its source
        root via ``GIT_LOC``.
    :type libn: str
    :return: ``True`` if the import path exists in the library source tree
        and (for :class:`ast.ImportFrom`) the imported name is accessible
        there; ``False`` otherwise.
    :rtype: bool
    :raises ValueError: If ``import_node`` is neither an :class:`ast.Import`
        nor an :class:`ast.ImportFrom`.
    """

    lib_path = PIG_LIB_DIR / Path(GIT_LOC[libn])

    if ".py" in str(lib_path) or ".pyi" in str(lib_path):
        lib_path = lib_path.parent

    # Imported node might be related to another library
    if llm_pre.libname(libn) not in ast.unparse(import_node):
        return True

    # Convert Import node into accessible path
    if isinstance(import_node, ast.Import):
        for _name in import_node.names:
            if llm_pre.libname(libn) in _name.name:
                path_py = import_node.names[0].name.replace(".", "/") + ".py"
                path_pyi = import_node.names[0].name.replace(".", "/") + ".pyi"
                path = import_node.names[0].name.replace(".", "/")

                # libn file is python file
                tmp1 = Path(lib_path / Path(path_py))
                tmp2 = Path(lib_path / Path(path_pyi))

                # libn file is directory
                tmp3 = Path(lib_path.parent / Path(path))

                # lib_path is not python
                tmp4 = Path(lib_path.parent / Path(path_py))
                tmp5 = Path(lib_path.parent / Path(path_pyi))

                cond0 = tmp1.exists()
                cond1 = tmp2.exists()
                cond2 = tmp3.exists()
                cond3 = tmp4.exists()
                cond4 = tmp5.exists()

                if cond0 or cond1 or cond2 or cond3 or cond4:
                    return True
                else:
                    return False

    elif isinstance(import_node, ast.ImportFrom):
        path_py = import_node.module.replace(".", "/") + ".py"
        path_pyi = import_node.module.replace(".", "/") + ".pyi"
        path = import_node.module.replace(".", "/")

        tmp1 = Path(lib_path.parent / Path(path_py))
        tmp2 = Path(lib_path.parent / Path(path_pyi))
        tmp3 = Path(lib_path.parent / Path(path))
        tmp4 = Path(lib_path / Path(path_py))
        tmp5 = Path(lib_path / Path(path_pyi))
        tmp6 = Path(lib_path / Path(path))

        # Case Where alias is direct file
        cond0 = tmp1.exists()
        cond1 = tmp2.exists()

        # Case Where alias is directory
        cond2 = tmp3.exists()

        # Case Where alias is direct API
        cond3 = tmp4.exists()
        cond4 = tmp5.exists()
        cond5 = tmp6.exists()

        if cond0:
            apis1, apis2 = get_accessible_apis(tmp1, libn)

        if cond1:
            apis1, apis2 = get_accessible_apis(tmp2, libn)

        if cond2:
            apis1, apis2 = get_accessible_apis(tmp3, libn, dir=True)

        if cond3:
            apis1, apis2 = get_accessible_apis(tmp4, libn)

        if cond4:
            apis1, apis2 = get_accessible_apis(tmp5, libn)

        if cond5:
            apis1, apis2 = get_accessible_apis(tmp6, libn, dir=True)

        exist = False
        cond_total = cond0 or cond1 or cond2 or cond3 or cond4 or cond5

        for _name in import_node.names:
            name = _name.name
            if (cond_total) and name in (apis1.keys() or apis2.keys()):
                exist = True

            # 이거 왜한거징
            if cond2 or cond5:
                cond3 = Path(
                    PIG_LIB_DIR / Path(GIT_LOC[libn]).parent / Path(path) / Path(name)
                ).exists()
                cond4 = Path(
                    PIG_LIB_DIR
                    / Path(GIT_LOC[libn]).parent
                    / Path(path)
                    / Path(name + ".py")
                ).exists()
                cond5 = Path(
                    PIG_LIB_DIR
                    / Path(GIT_LOC[libn]).parent
                    / Path(path)
                    / Path(name + ".pyi")
                ).exists()

                if cond3 or cond4 or cond5:
                    exist = True

        return exist

    else:
        print("Error: Unknown type")
        raise ValueError("Unknown type")
