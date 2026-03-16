from ..synth import llm_pre
from .utils import *

from .gits import GIT_LOC

import os, ast
from pathlib import Path
from typing import Union

PIG_LIB_DIR = os.environ.get("PIG_LIB_DIR")

from Cython.Compiler import Nodes, TreeFragment
from Cython.Compiler.Visitor import CythonTransform


# Main Function
def get_apis(lib_path, lib):
    if ".py" in str(lib_path):
        apis = get_all_apis(
            lib_path,
            str(lib_path).split("/")[-1].split(".")[0],
            lib,
            py=True,
        )
    else:
        apis = get_all_apis(lib_path, str(lib_path).split("/")[-1], lib)

    return apis


# Visiting an AST, and collecting all the api names and signature for Cython files
class GetAllApisCython(CythonTransform):
    """Extracts all APIs from a given library path, but in Cython files

    :param target_api: A tuple containing the original API name and its alias, if any. This is used when extracting specific APIs in the library.
    :type target_api: Union[str, None]
    """

    def __init__(self, target_api: Union[str, None] = None):
        self._classes = list()
        self._properties = list()
        self._functions = list()  # True If the new module uses libo, too
        self._methods = list()
        self._etcs = list()
        self.target_api = target_api

        self.name = None
        self.signs = dict()

    @property
    def classes(self):
        """Returns the list of extracted classes.
        :return: A list of tuples containing class names and their signatures.
        :rtype: list
        """
        return self._classes

    @property
    def properties(self):
        """Returns the list of extracted properties.
        :return: A list of tuples containing property names and their signatures.
        :rtype: list
        """
        return self._properties

    @property
    def functions(self):
        """Returns the list of extracted functions.
        :return: A list of tuples containing function names and their signatures.
        :rtype: list
        """
        return self._functions

    @property
    def methods(self):
        """Returns the list of extracted methods.
        :return: A list of tuples containing method names and their signatures.
        :rtype: list
        """
        return self._methods

    @property
    def etcs(self):
        """Returns the list of extracted miscellaneous items.
        :return: A list of tuples containing miscellaneous item names and their signatures.
        :rtype: list
        """
        return self._etcs

    def get_signs(
        self, node: Union[Nodes.ClassDefNode, Nodes.DefNode, Nodes.CFuncDefNode]
    ) -> list[str]:
        """Extracts the signatures from the given Cython AST node.
        :param node: The AST node from which to extract signatures. Can be a class or function node.
        :type node: Union[Nodes.ClassDefNode, Nodes.DefNode, Nodes.CFuncDefNode]
        :return: A list of argument names extracted from the node.
        :rtype: list[str]
        """
        values = []

        if isinstance(node, Nodes.ClassDefNode) or isinstance(
            node, Nodes.PyClassDefNode
        ):
            if isinstance(node.body, Nodes.StatListNode):
                for stmt in node.body.stats:

                    if isinstance(stmt, Nodes.CFuncDefNode) or isinstance(
                        stmt, Nodes.FuncDefNode
                    ):
                        try:
                            name = stmt.declarator.base.name
                        except:
                            name = stmt.name

                        # There exist the case where the class uses __init__ to define class
                        if (
                            isinstance(stmt, Nodes.CFuncDefNode)
                        ) and name == "__init__":
                            values = self.get_signs(stmt)
                            break

                        elif isinstance(stmt, Nodes.FuncDefNode) and name == "__init__":
                            values = self.get_signs(stmt)
                            break

        elif isinstance(node, Nodes.DefNode):
            try:
                values = [arg.declarator.name for arg in node.args]

            except:
                pass

            if node.star_arg != None:
                values.append(node.star_arg.name)

            if node.starstar_arg != None:
                values.append(node.starstar_arg.declarator.name)

            selfs_num = values.count("self")

            for _ in range(selfs_num):
                values.remove("self")

        elif isinstance(node, Nodes.CFuncDefNode):
            for arg in node.declarator.args:
                values.append(arg.declarator.declared_name())

            selfs_num = values.count("self")

            for _ in range(selfs_num):
                values.remove("self")

        else:
            pass

        return values

    def visit_ClassDefNode(self, node):
        tmp = self.name
        tmp_target_api = self.target_api
        vals = self.get_signs(node)

        try:
            name = node.name
        except:
            name = node.class_name

        if self.target_api == None:
            if self.name == None and not name.startswith("_"):
                self._classes.append((name, vals))

            else:
                self._methods.append((name, (vals, self.name)))

        else:
            if name == self.target_api[0] and self.name == None:
                self._classes.append((self.target_api[1], vals))

            self.target_api = None

        self.name = name
        self.visitchildren(node)
        self.name = tmp
        self.target_api = tmp_target_api

    def visit_PyClassDefNode(self, node):
        tmp = self.name
        vals = self.get_signs(node)

        try:
            name = node.name
        except:
            name = node.class_name

        if self.target_api == None and not name.startswith("_"):
            if self.name == None:
                self._classes.append((name, vals))

            else:
                self._methods.append((name, (vals, self.name)))

        else:
            if name == self.target_api[0] and self.name == None:
                self._classes.append((self.target_api[1], vals))

        self.name = name
        self.visitchildren(node)
        self.name = tmp

    def visit_DefNode(self, node):
        if not node.name.startswith("__") and not node.name.startswith("_"):
            tmp = self.name
            vals = self.get_signs(node)

            if self.target_api == None and not node.name.startswith("_"):
                if self.name == None:
                    self._functions.append((node.name, vals))
                else:
                    self._methods.append((node.name, (vals, self.name)))

            else:
                if node.name == self.target_api[0] and self.name == None:
                    self._functions.append((self.target_api[1], vals))

            self.name = node.name
            self.visitchildren(node)
            self.name = tmp

    def visit_CFuncDefNode(self, node):
        if not node.declarator.base.name.startswith(
            "__"
        ) and not node.declarator.base.name.startswith("_"):
            tmp = self.name
            vals = self.get_signs(node)

            if self.target_api == None:
                if self.name == None:
                    self._functions.append((node.declarator.base.name, vals))
                else:
                    self._methods.append((node.declarator.base.name, (vals, self.name)))

            else:
                if (
                    node.declarator.base.name == self.target_api[0]
                    and self.name == None
                ):
                    self._functions.append((self.target_api[1], vals))

            self.name = node.declarator.base.name
            self.visitchildren(node)
            self.name = tmp


# Visiting an AST, and collecting all the api names and signature
class GetAllApis(ast.NodeVisitor):
    """Extracts all APIs from a given library path.
    :param lib: The name of the library.
    :type lib: str

    :param py_path: The path to the current Python file.
    :type py_path: Union[str, Path]

    :param mapping: A boolean parameter indicating whether to consider self imports.
    :type mapping: bool

    :param typeshed_libs: A list of libraries available in typeshed.
    :type typeshed_libs: list

    :param target_api: A tuple containing the original API name and its alias, if any. This is used when extracting specific APIs in the library.
    :type target_api: Union[str, None]

    :param history: A dictionary to keep track of visited files to avoid circular imports. At Initial stage, it is None. It is updated during the recursive visits.
    :type history: Union[dict, None]
    """

    def __init__(
        self,
        lib: str,
        py_path: Union[str, Path],
        mapping: bool,
        typeshed_libs: list,
        target_api: Union[str, None] = None,
        history: Union[dict, None] = None,
    ):
        # Initializing API lists
        self._classes = list()
        self._properties = list()
        self._functions = list()
        self._methods = list()
        self._etcs = list()

        # Other parameters
        self.lib = lib
        self.name = None
        self.fname = None
        self.signs = dict()
        self.py_path = py_path  # Describe the path of current code
        self.mapping = mapping  # if True, we don't have to consider self import
        self.typeshed_libs = typeshed_libs
        self.target_api = target_api

        if history == None:
            self.history = dict()
            self.history[self.py_path] = set()

        else:
            self.history = history

    @property
    def classes(self):
        """Returns the list of extracted classes.
        :return: A list of tuples containing class names and their signatures.
        :rtype: list
        """
        return self._classes

    @property
    def properties(self):
        """Returns the list of extracted properties.
        :return: A list of tuples containing property names and their signatures.
        :rtype: list
        """
        return self._properties

    @property
    def functions(self):
        """Returns the list of extracted functions.
        :return: A list of tuples containing function names and their signatures.
        :rtype: list
        """
        return self._functions

    @property
    def methods(self):
        """Returns the list of extracted methods.
        :return: A list of tuples containing method names and their signatures.
        :rtype: list
        """
        return self._methods

    @property
    def etcs(self):
        """Returns the list of extracted miscellaneous items.
        :return: A list of tuples containing miscellaneous item names and their signatures.
        :rtype: list
        """
        return self._etcs

    def get_signs(
        self,
        node: Union[ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef],
    ) -> list[str]:
        """Extracts the signatures from the given AST node.
        :param node: The AST node from which to extract signatures. Can be a class or function node.
        :type node: Union[ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef]

        :return: A list of argument names extracted from the node.
        :rtype: list[str]
        """

        values = []

        if isinstance(node, ast.ClassDef):
            dec0 = False

            for decorator in node.decorator_list:
                if "define" in ast.unparse(decorator):
                    dec0 = True

            for stmt in node.body:
                # There exist the case where the class uses __init__ to define class
                if (
                    isinstance(stmt, ast.FunctionDef)
                    or isinstance(stmt, ast.AsyncFunctionDef)
                ) and stmt.name == "__init__":
                    values = self.get_signs(stmt)
                    break

                # There exist the case where the class uses attrs (using field or ib)
                if isinstance(stmt, ast.Assign) and (
                    "field(" in ast.unparse(stmt) or "ib(" in ast.unparse(stmt)
                ):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            values.append(target.id)

                # There exist the case where the class uses attrs (using define)
                if isinstance(stmt, ast.AnnAssign) and dec0:
                    values.append(stmt.target.id)

            # There exist the case where the class uses characteristic (using attributes).
            for decorator in node.decorator_list:
                if "attributes(" in ast.unparse(decorator) and isinstance(
                    decorator, ast.Call
                ):
                    for arg in decorator.args:
                        if isinstance(arg, ast.Constant):
                            values.append(arg.value)

                        if (
                            isinstance(arg, ast.Call)
                            and isinstance(arg.func, ast.Name)
                            and arg.func.id == "Attribute"
                        ):
                            for arg2 in arg.args:
                                if isinstance(arg2, ast.Constant):
                                    values.append(arg2.value)

        else:  # FunctionDef, AsyncFunctionDef
            arguments = node.args

            for posonlyarg in arguments.posonlyargs:
                values.append(posonlyarg.arg)

            for arg in arguments.args:
                values.append(arg.arg)

            if arguments.vararg:
                values.append(arguments.vararg.arg)

            for kwonlyarg in arguments.kwonlyargs:
                values.append(kwonlyarg.arg)

            if arguments.kwarg:
                values.append(arguments.kwarg.arg)

            selfs_num = values.count("self")

            for _ in range(selfs_num):
                values.remove("self")

        return values

    def visit_ClassDef(self, node: ast.ClassDef):
        tmp = self.name
        tmp_target_api = self.target_api
        vals = self.get_signs(node)

        if self.target_api == None:
            if self.name == None and not node.name.startswith("_"):
                self._classes.append((node.name, vals))

            else:
                if not node.name.startswith("_"):
                    self._methods.append(
                        (node.name, (vals, self.name))
                    )  # ClassDef is a method of another class

        else:
            if node.name == self.target_api[0] and self.name == None:
                self._classes.append((self.target_api[1], vals))

        self.name = node.name
        self.generic_visit(node)
        self.name = tmp
        self.target_api = tmp_target_api

    def visit_FunctionDef(self, node: ast.FunctionDef):
        tmp = self.fname
        vals = self.get_signs(node)

        if self.target_api == None:

            if (
                self.name == None
                and not node.name.startswith("__")
                and not node.name.startswith("_")
            ):
                self._functions.append((node.name, vals))

            else:
                if not node.name.startswith("__") and not node.name.startswith("_"):
                    self._methods.append((node.name, (vals, self.name)))

                elif node.name == "__truediv__":
                    self._methods.append((node.name, (vals, self.name)))

                for decorator in node.decorator_list:
                    if "property" in ast.unparse(
                        decorator
                    ) and not node.name.startswith("__"):
                        self._properties.append((node.name, (vals, self.name)))
        else:
            if node.name == self.target_api[0] and self.name == None:
                self._functions.append((self.target_api[1], vals))

        self.fname = node.name
        self.generic_visit(node)
        self.fname = tmp

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        tmp = self.fname
        vals = self.get_signs(node)

        if self.target_api == None:
            if (
                self.name == None
                and not node.name.startswith("__")
                and not node.name.startswith("_")
            ):
                self._functions.append((node.name, vals))
            else:
                if not node.name.startswith("__") and not node.name.startswith("_"):
                    self._methods.append((node.name, (vals, self.name)))

                for decorator in node.decorator_list:
                    if "property" in ast.unparse(
                        decorator
                    ) and not node.name.startswith("__"):
                        self._properties.append((node.name, (vals, self.name)))

        else:
            if node.name == self.target_api[0] and self.name == None:
                self._functions.append((self.target_api[1], vals))

        self.fname = node.name
        self.generic_visit(node)
        self.fname = tmp

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if self.target_api == None:
            # Self Imports
            if node.level > 0 or (
                node.module != None and llm_pre.libname(self.lib) in node.module
            ):
                # Assiging self.py_path
                self.py_path_tmp = self.py_path

                if node.level > 0:
                    for _ in range(node.level):
                        self.py_path_tmp = self.py_path_tmp.parent

                else:
                    try:
                        self.py_path_tmp = (
                            PIG_LIB_DIR / Path(GIT_LOC[(self.lib)]).parent
                        )

                    except:
                        # TypeShed
                        self.py_path_tmp = (
                            PIG_LIB_DIR / Path(GIT_LOC[(self.lib)]).parent
                        )

                # Check For Underbar Flag and cimplementation (confluent_kafka)
                underbar_flag = False
                cimpl = False

                if node.module != None:
                    modules = node.module.split(".")

                    for module in modules:
                        if module.startswith("_") and (not module.startswith("__")):
                            underbar_flag = True
                        if module == "cimpl":
                            cimpl = True

                # Search For Imports
                for alias in node.names:
                    if (not self.mapping) or underbar_flag or (alias.asname != None):
                        if alias.name == "*":
                            target_api = None
                        else:
                            if alias.asname == None:
                                target_api = (alias.name, alias.name)
                            else:
                                target_api = (alias.name, alias.asname)

                        node_module = node.module if node.module != None else ""

                        module_file = self.py_path_tmp / Path(
                            (node_module).replace(".", "/") + ".py"
                        )
                        dir_file = self.py_path_tmp / Path(
                            (node_module).replace(".", "/") + "/__init__.py"
                        )

                        module_file_pyx = self.py_path_tmp / Path(
                            (node_module).replace(".", "/") + ".pyx"
                        )

                        if module_file.exists() or (dir_file.exists()):

                            target_file = (
                                module_file if module_file.exists() else dir_file
                            )

                            if (
                                self.py_path not in self.history
                                or target_file not in self.history[self.py_path]
                            ):
                                try:
                                    self.history[self.py_path].add(target_file)

                                except:
                                    self.history[self.py_path] = set()
                                    self.history[self.py_path].add(target_file)

                                with open(target_file, "r") as f:
                                    code = f.read().strip()

                                    tree = ast.parse(code)
                                    visitor = GetAllApis(
                                        self.libo,
                                        target_file,
                                        self.mapping,
                                        self.typeshed_libs,
                                        target_api,
                                        self.history,
                                    )
                                    visitor.visit(tree)

                                    self._classes += visitor.classes
                                    self._properties += visitor.properties
                                    self._functions += visitor.functions
                                    self._methods += visitor.methods
                                    self._etcs += visitor.etcs

                                self.history[self.py_path].remove(target_file)

                        if module_file_pyx.exists():
                            if (
                                self.py_path not in self.history
                                or module_file_pyx not in self.history[self.py_path]
                            ):

                                try:
                                    self.history[self.py_path].add(module_file_pyx)
                                except:
                                    self.history[self.py_path] = set()
                                    self.history[self.py_path].add(module_file_pyx)

                                try:
                                    with open(module_file_pyx, "r") as f:
                                        code = f.read()

                                        tree = TreeFragment.parse_from_strings(
                                            str(module_file_pyx), code
                                        )
                                        visitor = GetAllApisCython(self.lib, target_api)
                                        visitor.visit(tree)

                                        self._classes += visitor.classes
                                        self._properties += visitor.properties
                                        self._functions += visitor.functions
                                        self._methods += visitor.methods
                                        self._etcs += visitor.etcs

                                except:
                                    print(module_file_pyx, "is not readable")
                                    # 177.json

                                self.history[self.py_path].remove(module_file_pyx)

                if cimpl:
                    for alias in node.names:
                        if alias.asname == None:
                            self._etcs.append((alias.name, []))
                        else:
                            self._etcs.append((alias.asname, []))

            # # TypeShed Imports
            elif (
                node.module != None and node.module.split(".")[0] in self.typeshed_libs
            ):
                for alias in node.names:
                    if alias.name == "*":
                        tmp_result: dict = typeshed(
                            node.module.split(".")[0]
                        )  # Just one depth

                        self._classes += tmp_result[node.module.split(".")[0]][0]
                        self._functions += tmp_result[node.module.split(".")[0]][2]
                        self._etcs += tmp_result[node.module.split(".")[0]][4]

                    else:
                        pass

        else:
            pass

    def visit_Assign(self, node: ast.Assign):
        if self.name == None and self.fname == None:
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    self._etcs.append((target.id, []))

        else:
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and (ast.unparse(target).split(".")[1].startswith("_") == False)
                ):
                    self._properties.append((target.attr, ([], self.name)))

                elif (
                    isinstance(target, ast.Name)
                    and self.fname == None
                    and (not target.id.startswith("_"))
                ):
                    self._properties.append((target.id, ([], self.name)))

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if self.name == None and self.fname == None:
            if isinstance(node.target, ast.Name):
                self._etcs.append((node.target.id, []))

    def visit_Global(self, node: ast.Global):
        for name in node.names:
            if not name.startswith("_"):
                self._etcs.append((name, []))


def get_all_apis(
    lib_path: Union[str, Path],
    imp_path: str,
    lib: str,
    typeshed_libs: list,
    py: bool = False,
    mapping: bool = False,
) -> dict:
    """Extracts all APIs from the specified library path.

    :param lib_path: The path to the library from which to extract APIs.
    :type lib_path: Union[str, Path]
    :param imp_path: The import path corresponding to the library.
    :type imp_path: str
    :param lib: The name of the library.
    :type lib: str

    :param typeshed_libs: A list of libraries available in typeshed.
    :type typeshed_libs: list

    :param py: A boolean parameter indicating whether current file is directory or module. Defaults to False.
    :type py: bool
    :param mapping: A boolean parameter indicating whether to consider self imports. Defaults to False.
    :type mapping: bool

    :return: A dictionary containing the extracted APIs categorized by their import paths. Detailed type can be found in the extract_apis function.
    :rtype: dict
    """

    if lib in typeshed_libs:
        return typeshed(lib)

    apis = dict()  # key: path | val: (apis, properties)

    try:
        file_list_py = [
            file
            for file in os.listdir(lib_path)
            if (
                (file.endswith(".py") or file.endswith(".pyi") or file.endswith(".pyx"))
                and (not file.startswith("_") or file == "__init__.py")
                and (not file == "setup.py")
            )
        ]

    except:
        file_list_py = [str(lib_path).split("/")[-1]]
        lib_path = lib_path.parent

    # Iterating __init__ first
    if "__init__.py" in file_list_py:
        file_list_py.remove("__init__.py")
        file_list_py = ["__init__.py"] + file_list_py

    elif "__init__.pyi" in file_list_py:
        file_list_py.remove("__init__.pyi")
        file_list_py = ["__init__.pyi"] + file_list_py

    for file in file_list_py:
        if file in ["examples", "example", "src"]:
            continue
        with open(lib_path / file, "r") as f:
            code = f.read().strip()

        if file.endswith(".pyx"):
            try:
                tree = TreeFragment.parse_from_strings(file, code)
                visitor = GetAllApisCython(lib=lib)
            except:
                continue

        else:
            tree = ast.parse(code)
            visitor = GetAllApis(lib, lib_path / file, mapping, typeshed_libs)

        visitor.visit(tree)

        v1n, v2n, v3n, v4n, v5n = (
            visitor.classes,
            visitor.properties,
            visitor.functions,
            visitor.methods,
            visitor.etcs,
        )

        if file == "__init__.py" or file == "__init__.pyi":
            try:
                v1, v2, v3, v4, v5 = apis[imp_path]
                apis[imp_path] = (v1 + v1n, v2 + v2n, v3 + v3n, v4 + v4n, v5 + v5n)

            except:
                apis[imp_path] = (v1n, v2n, v3n, v4n, v5n)

        elif (file != "__init__.py" and file != "__init__.pyi") and py == True:
            try:
                v1, v2, v3, v4, v5 = apis[imp_path]
                apis[imp_path] = (v1 + v1n, v2 + v2n, v3 + v3n, v4 + v4n, v5 + v5n)

            except:
                apis[imp_path] = (v1n, v2n, v3n, v4n, v5n)

        elif (file != "__init__.py" and file != "__init__.pyi") and py == False:
            try:
                apis[imp_path + "." + file.split(".")[0]] = (
                    v1n,
                    v2n,
                    v3n,
                    v4n,
                    v5n,
                )
            except:
                apis[imp_path + "." + file.split(".")[0]] = (v1n, v2n, v3n, v4n, v5n)

        elif (file == "__init__.py" or file == "__init__.pyi") and py == False:
            try:
                v1, v2, v3, v4, v5 = apis[imp_path]
                apis[imp_path] = (v1 + v1n, v2 + v2n, v3 + v3n, v4 + v4n, v5 + v5n)

            except:
                apis[imp_path] = (v1n, v2n, v3n, v4n, v5n)

        else:
            pass

    if py == False:
        folders = [
            folder
            for folder in os.listdir(lib_path)
            if (os.path.isdir(lib_path / folder))
        ]

        for folder in folders:
            if folder in ["examples", "example", "src"] or str(folder).startswith("_"):
                continue
            apis_new = get_all_apis(
                lib_path / folder, imp_path + "." + folder, lib, mapping=mapping
            )
            apis.update(apis_new)

    return apis


def typeshed(lib: str) -> dict:
    """Extracts all APIs from the typeshed library.
    :param lib: The name of the library.
    :type lib: str
    :return: A dictionary containing the extracted APIs categorized by their import paths. Detailed type can be found in the extract_apis function.
    :rtype: dict
    """
    typeshed_libs = [
        file.split(".")[0]
        for file in os.listdir(TYPESHED_PATH)
        if not file.startswith("_")
    ]

    pyi: Path = TYPESHED_PATH / (lib + ".pyi")
    _pyi: Path = TYPESHED_PATH / ("_" + lib + ".pyi")
    dir: Path = TYPESHED_PATH / lib

    result = dict()

    if pyi.exists():
        apis = get_all_apis(pyi, lib, lib, typeshed_libs, py=True)
        result = update_dict(result, apis)

    if _pyi.exists():
        apis = get_all_apis(_pyi, lib, lib, typeshed_libs, py=True)
        result = update_dict(result, apis)

    if dir.exists():
        apis = get_all_apis(dir, lib, lib, typeshed_libs, py=False)
        result = update_dict(result, apis)

    return result


def extract_apis(
    lib: str, lib_path: Union[str, Path], typeshed_path: Union[str, Path]
) -> dict[
    str : tuple[
        set[tuple[str, list]],
        set[tuple[str, list]],
        set[tuple[str, list]],
        set[tuple[str, list]],
        set[tuple[str, list]],
    ]
]:
    """Extracts API signatures from the specified library path.

    :param libn: A name of the library.
    :type libn: str

    :param libn_path: A path to the library.
    :type libn_path: Union[str, Path]

    :param typeshed_path: The path to the typeshed directory.
    :type typeshed_path: Union[str, Path]

    :return: A dictionary mapping file paths to tuples containing sets of API signatures. Each tuple contains sets for classes, properties, functions, methods, and other entities.
    :rtype: dict"""

    global TYPESHED_PATH
    TYPESHED_PATH = Path(typeshed_path)

    if ".py" in str(lib_path):
        apis = get_all_apis(
            lib_path,
            str(lib_path).split("/")[-1].split(".")[0],
            lib,
            py=True,
            mapping=True,
        )
    else:
        apis = get_all_apis(lib_path, str(lib_path).split("/")[-1], lib, mapping=True)

    return apis
