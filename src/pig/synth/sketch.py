import ast, sys
from os import path
from typing import Union
from pathlib import Path
import logging

try:
    from . import call, synthesis, llm_pre, fix_import, matching, stmt_types
except:
    import call, synthesis, llm_pre, fix_import, matching, stmt_types

from synth import *

try:
    from pig.slicing import slicing
    from mapping import gits, api_lst
except:
    if __package__ is None:
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
        from pig.slicing import slicing
        from mapping import gits, api_lst


# file open should not be changed
def build_in_function_filter(OldApi, Imports, OCN, parent) -> bool:
    # How the oldapi is imported? If directly imported : true else false
    def check(OldApi, Imports) -> bool:
        for i in Imports:
            # if isinstance(OldApi, ast.Import): Ignore this case

            if isinstance(i, ast.ImportFrom):
                for n in i.names:
                    if n.name == OldApi:
                        return True

        return False

    def filter(OCN, OldApi):
        if isinstance(OCN, ast.Name) and OCN.id == OldApi:
            OCN = call.FindExprParent(parent, OCN)

        if (
            isinstance(OCN, ast.Call)
            and isinstance(OCN.func, ast.Name)
            and OCN.func.id == OldApi
        ):
            return True

        return False

    if OldApi != "open":
        return False

    if check(OldApi, Imports):
        return False

    # As target api is indirectly imported, we can filter out the directly called methods
    return filter(OCN, OldApi)


def PreRequired(
    h,
    key,
    val,
    history,
    mappings,
    CENs,
    UnAssignedVarsO,
    ParentO,
    ParentN,
    coden,
    FuncDefs,
    OldApi: str,
    libn: str,
    libo: str,
    apis,
    b_imports: bool,
    b_surround: bool,
    rootb_str: str,
    roota_str: str,
    rooto: ast.AST,
    roota: ast.AST,
    has_dec=False,
):
    """Resolve unassigned variables in a migrated node by adding surround nodes and imports.

    For a given ``(key, val)`` pair representing an old-to-new API node
    mapping, identifies variables used in ``val`` that are not yet assigned
    in the new code (``target_names``), then attempts to satisfy them in two
    stages:

    1. **Surround nodes** (if ``b_surround`` is ``True``): calls
       :func:`synthesis.Surround` to find and insert neighbouring statements
       from the old code that define the remaining variables.
    2. **Import statements** (if ``b_imports`` is ``True``): calls
       :func:`fix_import.Importfind` with full path-checking for each
       variable still unresolved after stage 1; otherwise falls back to a
       direct import lookup (``check=False``).

    Variables that appear in ``CENs``, ``FuncDefs``, ``UnAssignedVarsO``,
    or the current variable rename ``mappings`` are excluded from
    ``target_names`` before resolution begins. If ``val`` references the old
    API name as a load (but not a store), it is added back to
    ``target_names`` to ensure the corresponding import is included.

    :param h: The current working AST being built up, modified in-place by
        :func:`synthesis.Surround`.
    :type h: ast.AST
    :param key: The original old API call node that triggered this migration
        step.
    :type key: ast.AST
    :param val: The new API node that replaces ``key``.
    :type val: ast.AST
    :param history: A mutable state dict tracking processed nodes; its
        ``'changes'`` entry is updated with any newly added surround nodes.
    :type history: dict
    :param mappings: The variable rename mapping from
        ``(old_name, scope_name)`` to candidate new names, used to exclude
        already-resolved variables from ``target_names``.
    :type mappings: dict
    :param CENs: The set of built-in and context-defined names to exclude
        from dependency resolution.
    :type CENs: set
    :param UnAssignedVarsO: A mapping from scope name to the set of
        variables that are unassigned in the old code's scope.
    :type UnAssignedVarsO: dict
    :param ParentO: The parent mapping of the old code as produced by
        :func:`call.ParentAst`.
    :param ParentN: The parent mapping of the new code as produced by
        :func:`call.ParentAst`.
    :param coden: The AST of the new (LLM-generated) code, passed to
        :func:`fix_import.Importfind` for import resolution.
    :type coden: ast.AST
    :param FuncDefs: The set of function names defined in the old code,
        excluded from ``target_names``.
    :type FuncDefs: set
    :param OldApi: The old API name; if referenced as a load in ``val``,
        it is added to ``target_names`` to ensure its import is retained.
    :type OldApi: str
    :param libn: The name of the new library.
    :type libn: str
    :param libo: The name of the original library.
    :type libo: str
    :param apis: The API map of the new library, passed through to
        :func:`fix_import.Importfind`.
    :param b_imports: If ``True``, resolve remaining variables to import
        statements using full path validation; otherwise use direct lookup.
    :type b_imports: bool
    :param b_surround: If ``True``, attempt to resolve unassigned variables
        by inserting surround nodes from the old code before falling back to
        imports.
    :type b_surround: bool
    :param rootb_str: The unparsed source string of the old code, passed
        through to :func:`synthesis.Surround` for GumTree matching.
    :type rootb_str: str
    :param roota_str: The unparsed source string of the new code, passed
        through to :func:`synthesis.Surround` for GumTree matching.
    :type roota_str: str
    :param rooto: The AST of the old code.
    :type rooto: ast.AST
    :param roota: The AST of the new code.
    :type roota: ast.AST
    :param has_dec: Reserved for future use. Defaults to ``False``.
    :type has_dec: bool
    :return: A tuple ``(h, NCImport, CENs1, history)`` where ``h`` is the
        updated working AST, ``NCImport`` is the set of newly resolved import
        nodes, ``CENs1`` is the updated set of resolved import names, and
        ``history`` is the updated history dict.
    :rtype: tuple[ast.AST, set, set, dict]
    """

    Vars = synthesis.UnusedVars()
    Vars.visit(h)
    NCImport = set()
    CENs1 = set()

    oVars = synthesis.UnusedVars(libo=llm_pre.libname(libo))
    oVars.visit(h)

    _, UAVs = synthesis.Vars(Vars.assigned, Vars.used)

    if isinstance(val, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        FCP = call.FindFCParent(ParentO, val, 2)
    else:
        FCP = call.FindFCParent(ParentO, val)

        if FCP == None:
            FCP = call.FindFCParent(ParentO, key)

    name = slicing.extract_name(FCP)

    # Real Variables which should be resolved through Import or Surround Nodes

    target_names = (
        UAVs[name]
        - ((UnAssignedVarsO[name]) - Vars.imports)
        - (CENs - {libn})
        - oVars.imports
        - FuncDefs
    )

    for (old, scope), _ in mappings.items():
        if scope == name and old in target_names:
            target_names = target_names - {old}

    oldapi = None
    assign_oldapi = None

    # What if the new api has same name with the old one?
    for node in ast.walk(val):
        if (
            isinstance(node, ast.Name)
            and node.id == OldApi
            and isinstance(node.ctx, ast.Load)
        ):
            oldapi = OldApi

        if (
            isinstance(node, ast.Name)
            and node.id == OldApi
            and isinstance(node.ctx, ast.Store)
        ):
            assign_oldapi = OldApi

    if oldapi != None and assign_oldapi == None:
        target_names.add(oldapi)

    if len(target_names) != 0:
        # First, Find Unassigned Variables in the New Code (It might be Function or Class or additional variables)

        if isinstance(val, (ast.With, ast.AsyncWith)):
            GPC = call.FindSSParent(ParentO, val, depth=2)
        else:
            GPC = call.FindSSParent(ParentO, val)

        if GPC == None:
            gp = h
        else:
            gp = GPC

        try:
            try:
                ind = slicing.bodyindex1(gp, val)
            except:
                ind = slicing.bodyindex1(gp, key)

        except:  # if 같은거 저기에 있는...
            New_GPC = call.FindRealParent(ParentO, gp, depth=2)

            if New_GPC == None:
                New_gp = h
            else:
                New_gp = New_GPC

            ind = slicing.bodyindex1(New_gp, gp)
            gp = New_gp  # To be checked

        # Which should not be counted as Unassigned Variables
        exceptions = Vars.imports | CENs | FuncDefs | UnAssignedVarsO[name]

        if b_surround:
            # Find For Surround Nodes
            h, SurNodes, remains = synthesis.Surround(
                h,
                key,
                val,
                target_names,
                h,
                gp,
                coden,
                history,
                mappings,
                ind,
                name,
                ParentO,
                ParentN,
                OldApi,
                FuncDefs,
                exceptions,
                libo,
                rootb_str,
                roota_str,
                rooto,
                roota,
            )

        else:
            remains = target_names
            SurNodes = set()

        # Update history['changes'] with SurNodes
        history["changes"] = history["changes"] | SurNodes

        # !!!!!!!!!!!! Second, Find the Import Statements !!!!!!!!!!!
        nodes = SurNodes | {val}

        for remain in remains:  # 이 remains가 제대로 uav를 할지는 감이 안옴
            if b_imports:  # Find the import stmts with PIG
                NCImportmp, CENs1 = fix_import.Importfind(
                    coden, nodes, remain, libo, libn, apis
                )

            else:  # Find the import stmts normally
                NCImportmp, CENs1 = fix_import.Importfind(
                    coden, nodes, remain, libo, libn, apis, check=False
                )

            NCImport = NCImport | NCImportmp
            CENs = CENs1 | CENs

    return (h, NCImport, CENs1, history)


def CENSubs(CENs: set[str], Vars: dict) -> dict:
    for CEN in CENs:
        for _, val in Vars.items():
            if CEN in val:
                val.remove(CEN)

    return Vars


def migrator(
    OldApi: str,
    OCNs,
    ParentN: dict,
    ParentO: dict,
    codeo: ast.AST,
    coden: ast.AST,
    libo: str,
    libn: str,
    history: dict[str, dict],
    FuncDefs,
    UnAssignedVarsO,
    CENs,
    OldTree1,
    codeo_str: str,
    coden_str: str,
    apis,
    b_imports=True,
    b_varmap=True,
    b_surround=True,
    b_postprocess=True,
    gumtree=True,
) -> ast.AST:
    """Migrate all old API call sites in ``codeo`` to their new API equivalents.

    For each old API call node in ``OCNs[OldApi]``, finds the corresponding
    new API node in ``coden`` via GumTree-based tree matching, applies
    variable rename mappings, resolves unassigned variables through surround
    nodes and import statements, and returns the fully migrated AST.

    The migration proceeds in four stages:

    1. **Classification** – partitions ``OCNs[OldApi]`` into normal
       statement nodes, decorator nodes, class-base nodes, exception
       handlers, and type-annotation args.
    2. **Matching** – for each normal node, uses :func:`matching.matcher`
       (or :func:`llm_pre.MatchName` for structural nodes) to find the
       corresponding new node in ``coden``. Nodes for which no match is
       found are added to ``del_nodes_cands`` for later removal.
    3. **Pre-processing** – for each ``(old, new)`` pair in ``result``,
       calls :func:`PreRequired` to insert surround nodes and import
       statements that satisfy unresolved variable references.
    4. **Post-processing** – applies variable rename mappings via
       :func:`total_mappings`, rewrites the working AST ``h`` in-place,
       and removes any nodes in ``del_nodes_cands`` that were not matched.

    Special cases handled during matching:

    - :class:`ast.ExceptHandler` nodes are matched at the handler or
      ``Try`` level and stored by their ``.type`` attribute.
    - :class:`ast.Name` nodes matched to :class:`ast.arg` are replaced
      by the argument's type annotation.
    - :class:`ast.With` / :class:`ast.AsyncWith` nodes are matched
      as whole context-manager statements.
    - Decorator nodes that match a :class:`ast.ClassDef` or
      :class:`ast.FunctionDef` have their bodies merged rather than
      replaced.

    :param OldApi: The old API name whose call sites are to be migrated.
    :type OldApi: str
    :param OCNs: A mapping from API name to the list of AST nodes where
        that API is used, as produced by :class:`call.Preparation`.
    :param ParentN: The parent mapping of the new code as produced by
        :func:`call.ParentAst`.
    :type ParentN: dict
    :param ParentO: The parent mapping of the old code as produced by
        :func:`call.ParentAst`.
    :type ParentO: dict
    :param codeo: The AST of the original (old API) code.
    :type codeo: ast.AST
    :param coden: The AST of the new (LLM-generated) code.
    :type coden: ast.AST
    :param libo: The name of the original library.
    :type libo: str
    :param libn: The name of the new library.
    :type libn: str
    :param history: A mutable state dict tracking processed nodes and
        accumulated changes across multiple ``SketchMaker`` calls.
    :type history: dict[str, dict]
    :param FuncDefs: The set of function names defined in the old code,
        excluded from variable dependency resolution.
    :param UnAssignedVarsO: A mapping from scope name to the set of
        variables unassigned in the old code's scope.
    :param CENs: The set of built-in and context-defined names to exclude
        from dependency resolution.
    :type CENs: set
    :param OldTree1: The GumTree representation of the old code, used by
        :func:`matching.var_divide` for sub-expression matching.
    :param ParentO1: An alternative parent mapping of the old code used
        for deeper ancestor lookups.
    :param codeo_str: The unparsed source string of the old code.
    :type codeo_str: str
    :param coden_str: The unparsed source string of the new code.
    :type coden_str: str
    :param apis: The API map of the new library, passed to
        :func:`fix_import.Importfind` and :func:`matching.filter_stmt`.
    :param b_imports: If ``True``, resolve unassigned variables to import
        statements using full path validation. Defaults to ``True``.
    :type b_imports: bool
    :param b_varmap: If ``True``, apply variable rename mappings to the
        migrated nodes. Defaults to ``True``.
    :type b_varmap: bool
    :param b_surround: If ``True``, insert surround nodes from the old code
        to satisfy unresolved variable references. Defaults to ``True``.
    :type b_surround: bool
    :param b_postprocess: If ``True``, run the post-processing step to apply
        rename mappings and clean up deleted nodes. Defaults to ``True``.
    :type b_postprocess: bool
    :param gumtree: If ``True``, use the custom GumTree matcher
        (``ours.jar``); otherwise use the default matcher. Defaults to
        ``True``.
    :type gumtree: bool
    :return: The migrated AST with all matched old API nodes replaced by
        their new equivalents, surround nodes inserted, and imports resolved.
    :rtype: ast.AST
    """

    # Variable Extracting
    VarsO = synthesis.VarExtractor()
    VarsN = synthesis.VarExtractor()
    VarsO.visit(codeo)
    VarsN.visit(coden)

    # FuncDefs
    FuncDefs = set(call.FunctionDefs(codeo, ParentO).keys())

    # Basic node list
    temp1 = []
    temp2 = []

    result = dict()

    # Decorator node list
    Dtemp1 = dict()

    dec_to_stmt = dict()

    # Find Import stmts
    NCImport = set()

    HAS_NCNP = False  # True when new api nodes are found
    HAS_DEC = False  # True when decorators should be changed
    HAS_CB = False  # True when class base is found

    nodeo = None
    h = codeo

    mappings = dict()
    del_nodes_cands = set()

    print("=" * 50)
    print("OldApi:", OldApi)

    if OldApi in OCNs.keys():
        for o in OCNs[OldApi]:
            if isinstance(o, ast.ExceptHandler):
                temp1.append(o)

            elif isinstance(o, tuple) and o[2] == "decorator":
                HAS_DEC = True
                Dtemp1[o[1]] = o[0]  # key: : node | func or class node

            elif isinstance(o, tuple) and o[2] == "classbase":
                HAS_CB = True
                temp1.append(o[0])

            elif isinstance(o, tuple) and o[2] == "handler":
                temp1.append(o[0])  # similarity excepthandler itself but

            elif isinstance(o, ast.arg):
                # type_annotation
                temp1.append(o)

            # Just Normal Nodes
            else:
                Imports = [
                    n
                    for n in ast.walk(codeo)
                    if isinstance(n, (ast.Import, ast.ImportFrom))
                ]
                if build_in_function_filter(OldApi, Imports, o, ParentO):
                    continue

                ORP: Union[ast.If, ast.While, ast.For, ast.AsyncFor] = (
                    call.FindRealParent(ParentO, o, 1)
                )
                if type(ORP) in {ast.If, ast.While}:  # If.test | While.test
                    temp1.append(ORP.test)

                elif type(ORP) in {ast.For, ast.AsyncFor}:  # For.iter | AsyncFor.iter
                    temp1.append(ORP.iter)

                else:
                    temp1.append(ORP)

    # Normal Nodes
    for nodeo in temp1:
        if nodeo == None:
            continue

        nodeo, node4match = matching.notstmt(nodeo, OldApi)

        if isinstance(
            node4match,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.ExceptHandler,
            ),
        ):
            NewNode, _ = llm_pre.MatchName(
                nodeo, coden, ParentO, ParentN, mappings, HAS_DEC, HAS_CB, libo, libn
            )

        else:
            MNresult, NewNode = matching.matcher(
                codeo_str, coden_str, node4match, coden, h, api=OldApi, gumtree=gumtree
            )

        if NewNode != None:
            NewNode2 = NewNode
            HAS_NCNP = True
            check = True

            if gumtree:
                check = matching.filter_stmt(NewNode, nodeo, apis, coden, OldApi)

            if check:
                if isinstance(nodeo, ast.ExceptHandler) and isinstance(
                    NewNode, ast.ExceptHandler
                ):
                    NewNode = NewNode.type
                    result[nodeo.type] = NewNode

                elif isinstance(nodeo, ast.ExceptHandler) and isinstance(
                    NewNode, ast.Try
                ):
                    NewNode = NewNode.handlers[0]
                    result[nodeo] = NewNode

                elif isinstance(nodeo, ast.Name) and isinstance(NewNode, ast.arg):
                    NewNode = NewNode.annotation
                    result[nodeo] = NewNode

                elif isinstance(nodeo, (ast.With, ast.AsyncWith)) and isinstance(
                    NewNode, (ast.With, ast.AsyncWith)
                ):
                    result[nodeo] = NewNode

                else:
                    try:
                        result[MNresult] = NewNode
                    except:
                        result[nodeo] = NewNode

                # recording log for our gumtree
                try:
                    logging.info(f"Ours: {ast.unparse(NewNode)}")
                except:
                    logging.info("Ours: cannot unparse")

                if NewNode not in temp2:
                    temp2.append(NewNode)

            else:
                if gumtree:
                    NewNode1 = matching.var_divide(nodeo, NewNode, OldTree1, coden)

                    if NewNode != NewNode1:
                        try:
                            result[MNresult] = NewNode1
                        except:
                            result[nodeo] = NewNode1

                        try:
                            logging.info(f"Ours: {ast.unparse(NewNode)}")
                        except:
                            logging.info("Ours: cannot unparse")

                    else:
                        del_nodes_cands.add(nodeo)
                        logging.info(f"Deleted Node for: {ast.unparse(nodeo)}")

                else:
                    try:
                        result[MNresult] = NewNode
                    except:
                        result[nodeo] = NewNode

                    try:
                        logging.info(f"Ours: {ast.unparse(NewNode)}")
                    except:
                        logging.info("Ours: cannot unparse")

        else:
            # NewNode2 = None
            logging.info(
                (
                    "Ours: Deleted Nodefor Node %s" % ast.unparse(nodeo)
                    if nodeo
                    else "None"
                ),
            )

            del_nodes_cands.add(nodeo)

    # Decorator Nodes
    for key, val in Dtemp1.items():  # node, clsorfunc
        # key: decorator node | func or class node
        _, NewNode = matching.matcher(
            codeo_str, coden_str, key, coden, h, dec=HAS_DEC, gumtree=gumtree
        )

        # Decorator to Decorator
        if NewNode != None and isinstance(NewNode, tuple(stmt_types.expr)):
            HAS_NCNP = True
            HAS_DEC = True
            result[key] = NewNode
            NewNode1 = NewNode
            logging.info("Ours: %s", ast.unparse(NewNode1))

        # Decorator to class or function
        elif NewNode != None and isinstance(NewNode, (ast.ClassDef, ast.FunctionDef)):
            # Simple Implementation Now
            val.body += NewNode.body
            del_nodes_cands.add(key)

        # Decorator to other nodes
        elif NewNode != None and not isinstance(
            NewNode, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            if val.name in dec_to_stmt:
                # Find the existing node
                index = val.body.index(dec_to_stmt[val.name][0])
                val.body.insert(index + 1, NewNode)

            else:
                dec_to_stmt[val.name] = tuple([NewNode])
                val.body.insert(0, NewNode)

            del_nodes_cands.add(key)

        else:

            # print("not matched")
            NewNode1 = None
            del_nodes_cands.add(key)
            logging.info("Ours: Deleted Node for")

    # Class Base Nodes
    if HAS_CB and not HAS_DEC:
        result = llm_pre.MatchSim(
            temp1, temp2, OldApi, ParentO, ParentN, typ="classbase"
        )

    ParentO = call.ParentAst(h)
    stack = (
        set()
    )  # Already used for transplanting # 이게 하나에 여러개가 매핑이 되니까 하나 바꿨을때 딴것도 바뀜...

    # ===================================================== Transplant =============================================================
    for key, val in result.items():
        if val == None:
            continue

        if isinstance(key, (ast.ClassDef)) and isinstance(val, (ast.ClassDef)):
            ukey = ast.ClassDef(
                name=key.name,
                bases=key.bases,
                keywords=[],
                decorator_list=key.decorator_list,
                body=[],
                type_params=[],
            )
            uval = ast.ClassDef(
                name=val.name,
                bases=val.bases,
                keywords=[],
                decorator_list=val.decorator_list,
                body=[],
                type_params=[],
            )

            print("Class | key:", ast.unparse(ukey), "| val:", ast.unparse(uval))

        elif isinstance(key, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            val, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            ukey = ast.FunctionDef(
                name=key.name, args=key.args, decorator_list=key.decorator_list, body=[]
            )
            uval = ast.FunctionDef(
                name=val.name, args=val.args, decorator_list=val.decorator_list, body=[]
            )

            print("Function | key:", ast.unparse(ukey), "| val:", ast.unparse(uval))

        else:

            print("key:", ast.unparse(key), "| val:", ast.unparse(val), key, val)

        name1 = llm_pre.scope_name(key, val, ParentO)
        name2 = llm_pre.scope_name(val, key, ParentN)

        # If the new api is already implemented, skip the transplant
        if key in history["changes"]:
            continue

        # Looking for variable mappings
        if b_varmap:
            mappings = matching.total_mappings(
                h,
                coden,
                ast.unparse(coden),
                ParentO,
                mappings,
                libo,
                libn,
                OldApi,
                nodeo=key,
                noden=val,
                name1=name1,
                name2=name2,
            )  # key: old, val: new

        print("mappings:", mappings)

        # Modify LLM code if needed (var def change)
        if val != None and (not isinstance(val, ast.Name)) and b_varmap:
            _, val, _ = llm_pre.ModDefVars(key, val, mappings, CENs, ParentO, stack)
            MUVC = llm_pre.ModUseVars(mappings, FuncDefs, ParentN)
            val = MUVC.visit(val)

        # Transplant the corresponding node
        if HAS_NCNP:
            if isinstance(
                val, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and not isinstance(key, (ast.FunctionDef, ast.AsyncFunctionDef)):
                h = synthesis.stmt_to_dec(key, val, h, ParentO, FuncDefs)
                del_nodes_cands.add(key)

            else:
                SSC = synthesis.SynthSame(key, val, history["changes"], ParentO, HAS_CB)
                h = ast.fix_missing_locations(SSC.visit(h))

                result[key] = SSC.NCNP
                history["changes"] = SSC.history

                # Case Where ast.Assign became ast.With
                if SSC.HAS_W:
                    TRC = synthesis.TrimRoot(SSC.W_stmts, SSC.NCNP)
                    h = TRC.visit(h)

        ParentO = call.ParentAst(h)  # Update ParentO as h is changed with SynthSame

        # ========================= Finding Pre-required(Surround) Apis and variables ============================
        ParentO = call.ParentAst(h)
        FuncDefs = set(call.FunctionDefs(h, ParentO).keys())

        (h, NCImportmp, CENs1, history) = PreRequired(
            h,
            key,
            val,
            history,
            mappings,
            CENs,
            UnAssignedVarsO,
            ParentO,
            ParentN,
            coden,
            FuncDefs,
            OldApi,
            libn,
            libo,
            apis,
            b_imports,
            b_surround,
            ast.unparse(OldTree1),
            coden_str,
            OldTree1,
            coden,
        )

        NCImport = NCImport | NCImportmp
        CENs = CENs1 | CENs

        if b_postprocess:
            # ================================== Modify Function with Async ====================================
            ParentO = call.ParentAst(h)  # Update ParentO
            FParent = call.FindFParent(ParentO, val)

            if FParent != None and isinstance(FParent, ast.FunctionDef):
                for new_val in set(history["changes"]) | {val}:
                    if llm_pre.is_async(new_val):
                        AFDC = synthesis.AsyncFD(FParent, True, False)
                        h = AFDC.visit(h)

        history["changes"].add(key)
        history["changes"].add(val)

    for del_node in del_nodes_cands:

        if HAS_DEC:
            h = synthesis.SynthDel(
                [del_node], dict(), dict(), history["changes"], dec=True
            ).visit(h)

        else:
            h = synthesis.SynthDel(
                [del_node], dict(), dict(), history["changes"]
            ).visit(h)

    # ================================================Adding decorators in function or class=================================================
    if HAS_DEC and dec_to_stmt != {} and b_surround:
        ParentO = call.ParentAst(h)
        FuncDefs = set(call.FunctionDefs(h, ParentO).keys())

        key = dec_to_stmt[list(dec_to_stmt.keys())[0]][0]

        (h, NCImportmp, CENs1, history) = PreRequired(
            h,
            None,
            key,
            history,
            mappings,
            CENs,
            UnAssignedVarsO,
            ParentO,
            ParentN,
            coden,
            FuncDefs,
            OldApi,
            libn,
            libo,
            apis,
            b_imports,
            b_surround,
            ast.unparse(OldTree1),
            coden_str,
            OldTree1,
            coden,
            has_dec=True,
        )

        NCImport = NCImport | NCImportmp
        CENs = CENs1 | CENs

    # ============================================Recording Import history=============================================

    history["import"] = history["import"] | set([ast.unparse(imp) for imp in NCImport])

    return (history, h, CENs)


def FinalSynth(
    history,
    OldTree,
    UnusedVarsO,
    UnAssignedVarsO,
    CENs: set[str],
    FuncDefs,
    libo,
    libn,
    b_postprocess=False,
):
    NewTree = OldTree
    Imports = set()

    for i in history["import"]:
        try:
            Imports.add(ast.parse(i))
        except SyntaxError:
            continue

    # Deleting Import Statement from old library
    libo_real = llm_pre.libname(libo)
    IDC = synthesis.ImportDeleter(libo_real)
    NewTree = IDC.visit(NewTree)

    # Addinig Import Statements from new library
    SIC = synthesis.SynthImport(Imports)
    NewTree = SIC.visit(NewTree)  # OldTree

    # ====================================Preparation====================================

    VEC = synthesis.VarExtractor(check=True)
    VEC.visit(NewTree)

    VarsN = synthesis.UnusedVars()
    VarsN.visit(NewTree)

    UnUsedVarsN = synthesis.Vars(
        synthesis.Vars(VarsN.assigned, VarsN.used)[0], UnusedVarsO
    )[0]
    UnUsedVarsN = CENSubs(VEC.imports | CENs, UnUsedVarsN)
    UnAssignedVarsN = synthesis.Vars(
        synthesis.Vars(VarsN.assigned, VarsN.used)[1], UnAssignedVarsO
    )[0]
    UnAssignedVarsN = CENSubs(VEC.imports | CENs | FuncDefs, UnAssignedVarsN)

    # ====================================Unassigned variables deletion====================================

    # if b_postprocess:
    #     SDC = synthesis.SynthDel(
    #         [], UnAssignedVarsN, dict(), history=history["changes"]
    #     )  # unassigned dels
    #     NewTree = SDC.visit(NewTree)

    # tmp_NewTree = ast.unparse(ast.fix_missing_locations(NewTree))

    # ====================================UnUsed variables deletion====================================

    # if check:
    #     while True:
    #         SDC = synthesis.SynthDel(
    #             [], dict(), UnUsedVarsN, history=history["changes"], usedvars=VarsN.used
    #         )  # unused dels
    #         NewTree = SDC.visit(NewTree)
    #         if tmp_NewTree == ast.unparse(ast.fix_missing_locations(NewTree)):
    #             break
    #         tmp_NewTree = ast.unparse(ast.fix_missing_locations(NewTree))

    # ====================================Import stmts Mod====================================
    # Remove Duplicated Import stmts
    NewTree = llm_pre.DupImpSolver(NewTree)
    NewTree = slicing.fill_pass(NewTree)

    return NewTree


# Var Extraction
def preparation(code: str, apios: list[str], libo, libn):
    root = ast.parse(code)
    parent = call.ParentAst(root)

    CNC = call.Preparation([], apios=apios)
    CNC.visit(root)
    call_nodes = CNC.nodes

    Vars = synthesis.UnusedVars()
    Vars.visit(root)

    unused_vars, unassigned_vars = synthesis.Vars(Vars.assigned, Vars.used)
    funcdefs = set(call.FunctionDefs(root, parent).keys())

    return root, parent, call_nodes, unused_vars, unassigned_vars, funcdefs
