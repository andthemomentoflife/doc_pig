import copy
import ast, autoflake
from typing import Union

from ..synth import call, synthesis
from ..synth.stmt_types import stmt as stmt_type


def extract_name(
    node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module],
):
    """Get the name of the node.

    :param node: The AST node to extract the name from.
    :type node: Union[ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module]

    :return: The name of the node, or ``'module'`` if the node is an
        :class:`ast.Module` or ``None``, or ``None`` if the node type is unrecognized.
    :rtype: Optional[str]
    """

    if isinstance(node, ast.FunctionDef):
        return node.name
    elif isinstance(node, ast.AsyncFunctionDef):
        return node.name
    elif isinstance(node, ast.ClassDef):
        return node.name
    elif isinstance(node, ast.Module) or node == None:
        return "module"
    else:
        print("Failure in extract_name", type(node))
        return None


def delete_docstrings(root: ast.Module):
    """Remove all docstrings from the AST.

    Walks the entire AST and strips the first expression statement from
    function and class definitions if it is a string literal (i.e. a docstring).

    :param root: The root AST module node to process.
    :type root: ast.Module
    :return: The modified AST module with all docstrings removed.
    :rtype: ast.Module
    """
    for node in ast.walk(root):
        # let's work only on functions & classes definitions
        if not isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            continue
        if not len(node.body):
            continue
        if not isinstance(node.body[0], ast.Expr):
            continue
        if not hasattr(node.body[0], "value") or not isinstance(
            node.body[0].value, ast.Str
        ):
            continue
        node.body = node.body[1:]
    return root


def fill_pass(root: ast.AST) -> ast.AST:
    """Fill empty bodies with ``ast.Pass()`` to avoid syntax errors.

    Walks the entire AST and appends a :class:`ast.Pass` node to any
    empty body block found in functions, classes, control flow statements,
    exception handlers, and modules.

    Affected node types:

    - :class:`ast.FunctionDef`, :class:`ast.AsyncFunctionDef`
    - :class:`ast.ClassDef`
    - :class:`ast.With`, :class:`ast.AsyncWith`
    - :class:`ast.If`, :class:`ast.For`
    - :class:`ast.Try`, :class:`ast.ExceptHandler`
    - :class:`ast.Module`

    :param root: The root AST node to process.
    :type root: ast.AST
    :return: The modified AST with all empty bodies filled with ``ast.Pass()``.
    :rtype: ast.AST
    """
    # Node types that have a simple .body attribute
    _BODY_NODES = (
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.With,
        ast.AsyncWith,
        ast.If,
        ast.For,
        ast.Try,
        ast.ExceptHandler,
        ast.Module,
    )

    for node in ast.walk(root):
        if isinstance(node, _BODY_NODES) and node.body == []:
            node.body.append(ast.Pass())
    return root


def bodyindex1(p1, v1, check="default"):
    """Locate ``node`` within a body section of ``p1`` and return context.

    Searches ``body``, ``orelse``, ``finalbody``, and exception handler bodies
    (for :class:`ast.Try`) in order. The ``check`` parameter controls what is
    returned once the node is found.

    :param p1: The parent AST node to search within.
    :type p1: ast.AST
    :param node: The child AST node to locate.
    :type node: ast.AST
    :param check: Controls the return value:

        - ``'default'``: return the integer index of ``node``.
        - ``'aft'``: return the slice of the body after ``node``
          (or the full body if ``node`` is last).
        - ``'bef'``: return the sibling immediately before ``node``,
          or ``None`` if ``node`` is first.
        - any other value: return the sibling immediately after ``node``,
          or ``None`` if ``node`` is last.

    :type check: str
    :return: An index, a list of nodes, a single sibling node, or ``None``
        depending on ``check`` and the position of ``node``.
    :rtype: int | list[ast.AST] | ast.AST | None
    """

    try:
        try:
            ind = p1.body.index(v1)
            if check == "default":
                return ind

            elif check == "aft":
                try:
                    return p1.body[ind + 1 :]
                except:
                    return p1.body

            else:
                if (check == "bef") and (ind > 0):
                    return p1.body[ind - 1]

                elif check == "bef":
                    return None

                else:
                    try:
                        return p1.body[ind + 1]
                    except:
                        return None

        except:
            ind = p1.orelse.index(v1)
            if check == "default":
                return ind

            elif check == "aft":
                try:
                    return p1.orelse[ind + 1 :]
                except:
                    return p1.oreelse

            else:
                if (check == "bef") and (ind > 0):
                    return p1.orelse[ind - 1]

                elif check == "bef":
                    return None

                else:
                    try:
                        return p1.orelse[ind + 1]
                    except:
                        return None

    except:
        try:
            ind = p1.finalbody.index(v1)
            if check == "default":
                return ind

            elif check == "aft":
                try:
                    return p1.finalbody[ind + 1 :]
                except:
                    return p1.finalbody

            else:
                if (check == "bef") and (ind > 0):
                    return p1.finalbody[ind - 1]

                elif check == "bef":
                    return None

                else:
                    try:
                        return p1.finalbody[ind + 1]
                    except:
                        return None
        except:
            if isinstance(p1, ast.Try):
                for handler in p1.handlers:
                    if v1 in handler.body:
                        if check == "default":
                            return handler.body.index(v1)

                        elif check == "aft":
                            try:
                                return handler.body[handler.body.index(v1) + 1 :]
                            except:
                                return handler.body

                        else:
                            if check == "bef" and handler.body.index(v1) > 0:
                                return handler.body[handler.body.index(v1) - 1]

                            elif check == "bef":
                                return None

                            else:
                                try:
                                    return handler.body[handler.body.index(v1) + 1]
                                except:
                                    return None

    # raise Exception('Error in bodyindex1')


def FCTuple(root):
    """Return the ``__init__`` method of a class if it exists, otherwise the class itself.

    :param root: The class definition node to inspect.
    :type root: ast.ClassDef
    :return: The ``__init__`` :class:`ast.FunctionDef` node if present,
        otherwise ``root`` itself.
    :rtype: ast.FunctionDef | ast.ClassDef
    """

    # ClassBase & ClassDef | Decorator & ClassDef
    if isinstance(root, ast.ClassDef):
        for stmt in root.body:
            if isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
                return stmt
    return root  # If there's no __init__ function return the original node


def body_index(parent, node):
    """Find the index of ``node`` within the body of ``parent``.

    Searches through the possible body sections of ``parent`` in order:
    ``body``, ``orelse``, exception handlers (for :class:`ast.Try`), and
    ``finalbody``. Returns the first match found.

    :param parent: The parent AST node whose body sections are searched.
    :type parent: ast.AST
    :param node: The child AST node to locate.
    :type node: ast.AST
    :return: The index of ``node`` as a plain ``int`` if found in ``body``
        or ``orelse``; a ``(int, 'handler', ExceptHandler)`` tuple if found
        inside an exception handler's body; or ``None`` if not found in any
        section.
    :rtype: int | tuple[int, str, ast.ExceptHandler] | None
    """
    try:
        try:
            try:
                return parent.body.index(node)
            except:
                return parent.orelse.index(node)
        except:
            if isinstance(parent, ast.Try):
                for handler in parent.handlers:
                    if node in handler.body:
                        return (handler.body.index(node), "handler", handler)
            else:
                return None
    except:
        return parent.finalbody.index(node)

    return None


class ContextRemover(ast.NodeTransformer):
    """Remove irrelevant context nodes from the AST.

    Walks the AST and retains only nodes that are present in ``self.nodes``,
    pruning branches whose bodies become empty after transformation.

    :param nodes: The set of AST nodes to retain.
    :type nodes: set
    :param targets: Optional set of target nodes.
    :type targets: set
    :param blank: Whether to blank out removed nodes.
    :type blank: bool
    """

    def __init__(self, nodes, targets=set(), blank=False):
        self.nodes = nodes
        self.check = True
        self.targets = targets
        self.blank = blank

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old = self.check

        if node in self.nodes:
            self.check = False

            return node

        self.generic_visit(node)

        if node.body == [] or self.check or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if node.body == [] or self.check or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_ClassDef(self, node: ast.ClassDef):
        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if node.body == [] or self.check or node.body == [ast.Pass]:
            return None

        self.check = False
        return node

    def visit_Return(self, node: ast.Return):
        if node in self.nodes:
            self.check = False
            return node

        return None

    def visit_Delete(self, node: ast.Delete):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Assign(self, node: ast.Assign):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_AugAssign(self, node: ast.AugAssign):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_For(self, node: ast.For):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check or node.body == [] or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check or node.body == [] or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_While(self, node: ast.While):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check or node.body == [] or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_If(self, node: ast.If):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if (
            (node.body == [] or node.body == [ast.Pass])
            and (node.orelse == [] or node.orelse == [ast.Pass])
        ) or self.check:
            self.check = old
            return None

        self.check = False
        return node

    def visit_With(self, node: ast.With):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check or node.body == [] or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith):
        old = self.check

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check or node.body == [] or node.body == [ast.Pass]:
            self.check = old
            return None

        self.check = False
        return node

    def visit_Match(self, node: ast.Match):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Raise(self, node: ast.Raise):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Try(self, node: ast.Try):
        old = self.check

        if len(set(node.handlers) & self.nodes) > 0:
            self.check = False
            return node

        if node in self.nodes:
            self.check = False
            return node

        self.generic_visit(node)

        if self.check:
            self.check = old
            return None

        self.check = True

        for handler in node.handlers:
            if (handler.body != []) and (handler.body != [ast.Pass]):
                self.check = False

        if (
            (node.body != [] and node.body != [ast.Pass])
            or (node.orelse != [] and node.orelse != [ast.Pass])
            or (node.finalbody != [] and node.finalbody != [ast.Pass])
        ):
            self.check = False

        if self.check:
            self.check = old
            return None

        self.check = False
        return node

    def visit_Assert(self, node: ast.Assert):
        if node in self.nodes:
            self.check = False
            return node
        return None

    # def visit_Import
    # def visit_Importfrom

    def visit_Global(self, node: ast.Global):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Nonlocal(self, node: ast.Nonlocal):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Expr(self, node: ast.Expr):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Pass(self, node: ast.Pass):
        return None

    def visit_Break(self, node: ast.Break):
        if node in self.nodes:
            self.check = False
            return node
        return None

    def visit_Continue(self, node: ast.Continue):
        if node in self.nodes:
            self.check = False
            return node
        return None


def index_info(ParentO, OCN):
    """Collect the body index of each ancestor node up to the module root.

    Walks up the AST from ``OCN`` to the root :class:`ast.Module` by
    repeatedly calling :func:`call.FindSSParent`, recording the index of
    each child within its parent's body along the way.

    :param ParentO: The parent object used to resolve ancestor relationships.
    :param OCN: The starting AST node (Original Current Node) to walk up from.
    :return: A mapping from each ancestor node to the index of its child
        in that node's body, from ``OCN`` up to the root module.
    :rtype: dict[ast.AST, int]
    """
    indexes = dict()
    PN = call.FindSSParent(ParentO, OCN, 1)  # Get the immediate parent of OCN
    while True:
        index = body_index(PN, OCN)  # Find OCN's position in PN's body
        indexes[PN] = index
        if isinstance(PN, ast.Module):  # Reached the root; stop traversal
            break
        OCN = PN  # Move one level up
        PN = call.FindSSParent(ParentO, PN, 2)  # Get the next ancestor
    return indexes


def find_use_node(
    root: ast.Module,
    targets: set,
    index: Union[int | tuple[int, str, ast.ExceptHandler]],
    libo: str,
):
    """Find the first node that uses any of the target names after the given index.

    Walks the AST and returns the first statement node (at or below ``root``)
    that references one of the ``targets`` names and appears after ``index``
    in the body order. Compound statements are inspected at their key
    sub-expression (e.g. ``test`` for ``if``/``while``, ``iter`` for ``for``).

    :param root: The AST module to search within.
    :type root: ast.Module
    :param targets: The set of names to look for.
    :type targets: set
    :param index: The body index after which to start matching. Either a plain
        ``int`` for top-level statements, or a ``(int, str, ExceptHandler)``
        tuple for nodes inside a ``try`` block.
    :type index: Union[int, tuple[int, str, ast.ExceptHandler]]
    :param libo: The library name passed to :class:`call.NameExtractor` to
        filter relevant name references.
    :type libo: str
    :return: A tuple of ``(matched_node, remaining_targets)`` where
        ``matched_node`` is the first node that uses a target name, or
        ``None`` if no match is found.
    :rtype: tuple[ast.AST | None, set]
    """

    for node in ast.walk(root):
        cond1 = type(node) in (
            set(stmt_type)
            - set(
                [
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.With,
                    ast.AsyncWith,
                    ast.Try,
                ]
            )
        )
        cond2 = isinstance(node, ast.If) or isinstance(node, ast.While)
        cond3 = isinstance(node, ast.For) or isinstance(node, ast.AsyncFor)
        cond4 = isinstance(node, ast.With) or isinstance(node, ast.AsyncWith)
        cond5 = isinstance(node, ast.Try)

        if cond1 or cond2 or cond3 or cond4 or cond5:
            if cond1 and isinstance(node, ast.Assign):
                node_copy = node.value
            elif cond1:
                node_copy = node
            elif cond2:
                node_copy = node.test
            elif cond3:
                node_copy = node.iter
            elif cond4:
                node_copy = node.items[0]  # Assume only one withitem exists
            elif cond5:
                continue
            else:
                pass

            NEC = call.NameExtractor(check1=True, libo=libo)
            NEC.visit(node_copy)
            new_index = body_index(root, node)

            if isinstance(index, int) and isinstance(new_index, int):
                cond1 = new_index > index
            elif isinstance(index, tuple) and isinstance(new_index, tuple):
                cond1 = new_index[0] > index[0]
            else:
                cond1 = True

            if len(set(NEC.list) & targets) > 0 and cond1:
                targets = targets - set(NEC.list)
                return (node, targets - set(NEC.list))

    return (None, targets)


def find_need_node(
    root: ast.Module,
    names: set,
    nodes: set,
    index: int | tuple[int, str, ast.ExceptHandler] | None,
    classdefs: dict,
    funcdefs: dict,
    libo: str,
    target0,
):
    """Find necessary nodes that define or modify the given names before the given index.

    Walks the AST to collect assignment, annotated assignment, and ``global``
    statement nodes that define any of the requested ``names``. Only nodes
    that appear before ``index`` in body order are considered, unless the
    node is already in ``nodes`` or ``target0`` is a function/class definition.
    Class and function definitions matching ``names`` are appended last.

    :param root: The AST module to search within.
    :type root: ast.Module
    :param names: The set of names whose defining nodes are being sought.
    :type names: set
    :param nodes: The accumulator set of already-collected nodes.
    :type nodes: set
    :param index: The body index before which to search. Either a plain
        ``int``, a ``(int, str, ExceptHandler)`` tuple for nodes inside a
        ``try`` block, or ``None`` to match all positions.
    :type index: int | tuple[int, str, ast.ExceptHandler] | None
    :param classdefs: A mapping from class name to its :class:`ast.ClassDef` node.
    :type classdefs: dict
    :param funcdefs: A mapping from function name to its
        :class:`ast.FunctionDef` / :class:`ast.AsyncFunctionDef` node.
    :type funcdefs: dict
    :param libo: The library name passed to :class:`call.NameExtractor` to
        filter relevant name references.
    :type libo: str
    :param target0: The node that triggered this search; excluded from results
        and used to determine index comparison behaviour.
    :return: A tuple of ``(nodes, remaining_names)`` where ``nodes`` is the
        updated set of collected nodes and ``remaining_names`` is the subset
        of ``names`` that could not be resolved.
    :rtype: tuple[set, set]
    """

    for node in ast.walk(root):
        if (
            isinstance(node, ast.Assign)
            or isinstance(node, ast.AnnAssign)
            or isinstance(node, ast.Global)
        ) and node != target0:
            targets = set()

            if isinstance(node, ast.Assign):
                for target in node.targets:
                    # Subscript is not a target
                    if isinstance(target, ast.Subscript):
                        continue

                    NEC = call.NameExtractor(check1=True, libo=libo)
                    NEC.visit(target)
                    targets = targets | set(NEC.list)

            elif isinstance(node, ast.AnnAssign):
                NEC = call.NameExtractor(check1=True, libo=libo)
                NEC.visit(node.target)
                targets = targets | set(NEC.list)

            else:
                for n in node.names:
                    targets.add(n)

            new_index = body_index(root, node)

            if isinstance(index, int) and isinstance(new_index, int):
                if (
                    isinstance(target0, ast.FunctionDef)
                    or isinstance(target0, ast.AsyncFunctionDef)
                    or isinstance(target0, ast.ClassDef)
                    and isinstance(root, ast.Module)
                ):
                    cond1 = True
                else:
                    cond1 = new_index < index
            elif isinstance(index, tuple) and isinstance(new_index, tuple):
                cond1 = new_index[0] < index[0]
            else:
                cond1 = True

            if len(targets & names) > 0 and (cond1 or (node in nodes)):
                nodes.add(node)
                names = names - targets

            elif len(targets & names) > 0 and cond1 and (node not in nodes):
                nodes.add(node)
                names = names - targets

            else:
                pass

    # Search for classdefs, funcdefs -> 마지막에만 해야함
    for c in set(classdefs.keys()) & names:
        nodes.add(classdefs[c])

    for f in set(funcdefs.keys()) & names:
        nodes.add(funcdefs[f])

    return (nodes, names)


def need_nodes(
    nodes: set, codeo, CENs, Imps, indexes, ParentO, funcdefs, classdefs, libo
):
    """Transitively collect all AST nodes required by the given seed nodes.

    Starting from ``nodes``, repeatedly extracts every name referenced by
    each node, resolves those names to their defining AST nodes via
    :func:`find_need_node`, and continues until no new nodes are discovered.

    :param nodes: The initial set of seed nodes whose dependencies are to
        be resolved.
    :type nodes: set
    :param codeo: The top-level module node used as the fallback search root
        when traversal reaches the module scope.
    :type codeo: ast.Module
    :param CENs: A set of built-in or context-defined names to exclude from
        dependency resolution.
    :type CENs: set
    :param Imps: A set of imported names to exclude from dependency resolution.
    :type Imps: set
    :param indexes: A mapping from each ancestor node to the body index of
        its relevant child, as produced by :func:`index_info`.
    :type indexes: dict
    :param ParentO: The parent-resolver object used to locate ancestor nodes
        via :func:`call.FindSSParent` and :func:`call.FindFParent`.
    :param funcdefs: A mapping from function name to its defining node,
        used to resolve name references to functions.
    :type funcdefs: dict
    :param classdefs: A mapping from class name to its defining node,
        used to resolve name references to classes.
    :type classdefs: dict
    :param libo: The library name passed to :class:`call.NameExtractor` to
        filter relevant name references.
    :type libo: str
    :return: The fully expanded set of nodes required to execute the seed nodes.
    :rtype: set
    """

    nodes_tmp = copy.copy(nodes)
    stack = copy.copy(nodes)
    history = set()
    names = set()

    while True:
        if len(stack) == 0:
            break

        target = stack.pop()

        if target == None or target in history:
            continue
        history.add(target)

        NEC = call.NameExtractor(check1=True, libo=libo)

        if isinstance(target, ast.Assign):
            for t in target.targets:
                if isinstance(t, ast.Subscript):
                    NEC.visit(t)
                    names = names | set(NEC.list)

                if isinstance(t, ast.Attribute):
                    NEC = call.NameExtractor(check=True, check1=True, libo=libo)
                    NEC.visit(t)

                    for name in NEC.list:
                        if "self." not in name:
                            names.add(name)

            NEC = call.NameExtractor(check1=True, libo=libo)
            NEC.visit(target.value)
            names = names | set(NEC.list)

        else:
            for node in ast.walk(target):
                # Case where it should be skipped
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Subscript):
                            NEC = call.NameExtractor(check1=True, libo=libo)
                            NEC.visit(t)
                            names = names | set(NEC.list)

                        if isinstance(t, ast.Attribute) and not "self" in ast.unparse(
                            t
                        ):
                            NEC = call.NameExtractor(check=True, check1=True, libo=libo)
                            NEC.visit(t)
                            names = names | set(NEC.list)

                    NEC = call.NameExtractor(check1=True, libo=libo)
                    NEC.visit(node.value)
                    names = names | set(NEC.list)

                elif isinstance(node, ast.AnnAssign):
                    if isinstance(node.target, ast.Subscript):
                        NEC = call.NameExtractor(check1=True, libo=libo)
                        NEC.visit(node.target)
                        names = names | set(NEC.list)

                    if isinstance(node.target, ast.Attribute):
                        NEC = call.NameExtractor(check=True, check1=True, libo=libo)
                        NEC.visit(node.target)
                        names = names | set(NEC.list)

                    if node.value != None:
                        NEC.visit(node.value)
                        names = names | set(NEC.list)

                elif type(node) in [
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Try,
                    ast.Module,
                ]:

                    cond2 = isinstance(node, ast.If) or isinstance(node, ast.While)
                    cond3 = isinstance(node, ast.For) or isinstance(node, ast.AsyncFor)
                    cond4 = isinstance(node, ast.With) or isinstance(
                        node, ast.AsyncWith
                    )

                    node_copy = None

                    if cond2:
                        node_copy = node.test
                    elif cond3:
                        node_copy = node.iter
                    elif cond4:
                        node_copy = node.items[0]  # Assume only one withitem exists

                    try:
                        NEC = call.NameExtractor(check1=True, libo=libo)
                        NEC.visit(node_copy)
                        names = names | set(NEC.list)

                    except:
                        pass

                elif type(node) in [ast.With, ast.AsyncWith]:
                    for item in node.items:
                        NEC = call.NameExtractor(check1=True, libo=libo)
                        NEC.visit(item)
                        names = names | set(NEC.list)

                elif type(node) in stmt_type:
                    Cparent = call.FindCParent(ParentO, node)
                    cond1 = (
                        isinstance(Cparent, ast.ClassDef)
                        and (Cparent.name in ast.unparse(node))
                        and ("super" in ast.unparse(node))
                    )  # super().__init__

                    if not cond1:
                        NEC.visit(node)
                        names = names | set(NEC.list)

                elif isinstance(node, ast.ListComp) or isinstance(node, ast.SetComp):
                    for c in node.generators:
                        NEC = call.NameExtractor(check1=True, libo=libo)
                        NEC.visit(c.target)
                        names = names - set(NEC.list)
                    break

                else:
                    pass

                # If function arg... no names - args
                Fparent = call.FindFParent(ParentO, node)
                if isinstance(Fparent, ast.FunctionDef) or isinstance(
                    Fparent, ast.AsyncFunctionDef
                ):
                    NEC4A = call.NameExtractor(check1=True, libo=libo)
                    NEC4A.visit(Fparent.args)
                    names = names - set(NEC4A.list)

        names = names - CENs - Imps

        if type(target) in [
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.If,
            ast.For,
            ast.AsyncFor,
            ast.While,
            ast.Try,
            ast.With,
            ast.AsyncWith,
        ]:
            FCP = call.FindSSParent(ParentO, target, 2)
        else:
            FCP = call.FindSSParent(ParentO, target, 1)

        while True:
            try:
                index = indexes[FCP]
            except:
                index = None

            if isinstance(FCP, ast.AsyncFunctionDef) or isinstance(
                FCP, ast.FunctionDef
            ):
                NEC4A = call.NameExtractor(check1=True, libo=libo)
                NEC4A.visit(FCP.args)

                for decorator in FCP.decorator_list:
                    NEC4D = call.NameExtractor(check1=True, libo=libo)
                    NEC4D.visit(decorator)
                    names = names | set(NEC4D.list)

                names = names - set(NEC4A.list)
                nodes, names = find_need_node(
                    FCP, names, nodes, index, classdefs, funcdefs, libo, target
                )

            elif isinstance(FCP, ast.ClassDef):
                init = FCTuple(FCP)
                if not isinstance(init, ast.ClassDef):
                    nodes.add(init)
                nodes, names = find_need_node(
                    FCP, names, nodes, index, classdefs, funcdefs, libo, target
                )

            elif isinstance(FCP, ast.For) or isinstance(FCP, ast.AsyncFor):
                NEC4I = call.NameExtractor(check1=True)
                NEC4I.visit(FCP.iter)
                names = names | set(NEC4I.list)
                nodes, names = find_need_node(
                    FCP, names, nodes, index, classdefs, funcdefs, libo, target
                )

            elif isinstance(FCP, ast.While) or isinstance(FCP, ast.If):
                NEC4T = call.NameExtractor(check1=True)
                NEC4T.visit(FCP.test)
                names = names | set(NEC4T.list)
                nodes, names = find_need_node(
                    FCP, names, nodes, index, classdefs, funcdefs, libo, target
                )

            elif isinstance(FCP, ast.With) or isinstance(FCP, ast.AsyncWith):
                for item in FCP.items:
                    NEC4I = call.NameExtractor(check1=True)
                    NEC4I.visit(item)
                    names = names | set(NEC4I.list)

                nodes, names = find_need_node(
                    FCP, names, nodes, index, classdefs, funcdefs, libo, target
                )

            elif isinstance(FCP, ast.Try):
                # 만약에 Excepthandler가 있으면 거기안에있는 Stmt 다 돌아야하고
                if isinstance(target, ast.ExceptHandler):
                    nodes.add(FCP)
                    nodes, names = find_need_node(
                        FCP, names, nodes, index, classdefs, funcdefs, libo, target
                    )
                else:
                    pass

            elif isinstance(FCP, ast.Module) or FCP == None or len(names) == 0:
                FCP = codeo
                nodes, names = find_need_node(
                    codeo, names, nodes, index, classdefs, funcdefs, libo, target
                )
                break

            else:
                break  # This doesn't happen

            FCP = call.FindSSParent(ParentO, FCP, 2)

        stack = ((nodes - nodes_tmp - history) | stack) - {None}

    return nodes


def slice(
    OCNs: dict,
    codeo: ast.AST,
    apio: str,
    ParentO: dict,
    libo: str,
    libn: str,
    funcdefs,
    classdefs,
    blank=False,
):
    """Slice the AST to retain only nodes relevant to the given API call sites.

    Performs a five-step program slice on ``codeo``:

    1. **Mark targets** – identify the AST nodes where the old API (``apio``)
       is used, handling special cases such as class bases, decorators, and
       exception handlers.
    2. **Mark use cases** – for ``Assign`` nodes, trace forward to find
       subsequent statements that consume the assigned names.
    3. **Mark dependencies** – transitively collect all nodes required to
       execute the targets via :func:`need_nodes`.
    4. **Remove context** – strip all nodes not in the final set using
       :class:`ContextRemover`.
    5. **Cleanup** – insert ``pass`` into empty bodies with :func:`fill_pass`
       and remove unused imports with ``autoflake``.

    :param OCNs: A mapping from API name to the list of AST nodes (Old Call
        Nodes) where that API is referenced.
    :type OCNs: dict
    :param codeo: The original AST module to slice.
    :type codeo: ast.AST
    :param apio: The name of the old API whose usage sites are the slice
        criteria.
    :type apio: str
    :param ParentO: The parent-resolver object used to locate ancestor nodes.
    :type ParentO: dict
    :param libo: The name of the original library, used to filter name
        references during dependency resolution.
    :type libo: str
    :param libn: The name of the new library, excluded from dependency
        resolution alongside ``libo``.
    :type libn: str
    :param funcdefs: A mapping from function name to its defining AST node.
    :param classdefs: A mapping from class name to its defining AST node.
    :param blank: If ``True``, passes the blank flag through to
        :class:`ContextRemover`. Defaults to ``False``.
    :type blank: bool
    :return: A new :class:`ast.Module` containing only the sliced code,
        parsed from the autoflake-cleaned unparsed output.
    :rtype: ast.Module
    """

    nodes_final = set()
    nodes = set()

    CENs = {
        "str",
        "ast",
        "os",
        "json",
        "sys",
        "__salt__",
        "len",
        "ValueError",
        "int",
        "float",
        libo,
        libn,
        "super",
        "range",
        "type",
        "AssertionError",
        "open",
        "all",
        "list",
        "isinstance",
        "Exception",
        "self",
        "bool",
        "bytes",
        "abort",
        "kwargs",
        "globals",
        "zip",
        "dict",
        "map",
        "max",
        "PermissionError",
        "enumerate",
        "__name__",
        "__file__",
        "ImportError",
        "IOError",
        "local",
        "lcd",
        "any",
        "IndexError",
        "print",
        "urllib",
        "set",
    }
    indexes = None

    VEC = synthesis.VarExtractor()
    VEC.visit(codeo)
    Imps = VEC.imports
    targets = set()  # Real api related nodes only

    if apio in OCNs.keys():
        for OCN in OCNs[apio]:
            # 1. Mark the targeted node
            if isinstance(OCN, tuple):  # classbase | decorator | handler
                if OCN[2] == "classbase":
                    nodes.add(FCTuple(OCN[0]))
                    targets.add(OCN[0])  # Add Class

                elif OCN[2] == "decorator":
                    # Only leave the target decorator
                    if OCN[0] in nodes:
                        OCN[0].decorator_list.append(OCN[1])
                        nodes.add(OCN[1])
                        targets.add(OCN[1])  # Add Function ... CLass...

                    else:
                        OCN[0].decorator_list = [OCN[1]]
                        nodes.add(OCN[0])
                        nodes.add(OCN[1])

                        targets.add(OCN[1])

                else:
                    nodes.add(OCN[0])

                    targets.add(OCN[0])  # Add ExceptHandler

            elif isinstance(OCN, ast.arg):
                fp = call.FindFParent(ParentO, OCN)
                nodes.add(fp)

            else:  # Usual Nodes
                nodes.add(OCN)
                OCN = call.FindRealParent(ParentO, OCN, 1)
                nodes.add(OCN)

                targets.add(OCN)

                indexes = index_info(ParentO, OCN)

                # 2. Mark the Use Case related to targeted node
                if isinstance(OCN, ast.Assign):
                    targets = set()
                    for target in OCN.targets:
                        if isinstance(target, ast.Name):
                            targets.add(target.id)

                        if isinstance(target, ast.Tuple):
                            for elt in target.elts:
                                if isinstance(elt, ast.Name):
                                    targets.add(elt.id)

                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and "self" in target.value.id
                        ):
                            targets.add("self." + target.attr)

                    targets = targets - CENs - Imps
                    OCN_copy = OCN
                    FCP = call.FindSSParent(ParentO, OCN, 1)

                    while True:
                        UseCase, targets = find_use_node(
                            FCP, targets, indexes[FCP], libo
                        )

                        if UseCase != None:
                            nodes.add(UseCase)

                        if (len(targets) == 0) or (
                            FCP == None or isinstance(FCP, ast.Module)
                        ):
                            break

                        OCN_copy = FCP
                        FCP = call.FindSSParent(ParentO, OCN_copy, depth=2)

            # 3. Mark the needed nodes for the targeted nodes with fixed point
            nodes = need_nodes(
                nodes, codeo, CENs, Imps, indexes, ParentO, funcdefs, classdefs, libo
            )
            nodes_final = nodes | nodes_final

    # 4. Remove the context which are not in targets
    if blank:
        # Add targets
        CR = ContextRemover(nodes_final, blank=blank)

    else:
        CR = ContextRemover(nodes_final, blank=blank)
    codea = CR.visit(codeo)

    # 5. Fill Pass | AutoFlake
    codea = fill_pass(codea)
    codea = autoflake.fix_code(
        (ast.unparse(ast.fix_missing_locations(codea))), remove_all_unused_imports=True
    )
    return ast.parse(codea)
