from pathlib import Path
import ast

from pig.synth.sketch import migrator, preparation
from pig.llm.query import ask_llm
from pig.mapping.compare_arg import api_mapping
from pig.mapping.api_lst import get_apis
from pig.synth.cens import CENs


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

OLD_LIB = "aiohttp"
NEW_LIB = "httpx"
TARGET_API = "get"

# Original code to migrate
ORIGINAL_CODE = """
import aiohttp

async def fetch(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()
"""

# Arguments of the original API
ORIGINAL_ARGS = ["url", "allow_redirects", "kwargs"]

# Path to the new library source
NEW_LIB_PATH = Path("path/to/httpx")

# LLM configuration
MODEL = ""  # e.g., "gpt-4"
ENGINE = ""  # "openai" or "ollama"
TEMPERATURE = 1


# ---------------------------------------------------------------------
# Step 1: Find candidate APIs
# ---------------------------------------------------------------------

candidates = api_mapping(
    apios=[TARGET_API],
    libo=OLD_LIB,
    libn=NEW_LIB,
    libn_path=NEW_LIB_PATH,
    argso=ORIGINAL_ARGS,
)

apins = [(name, spec) for name, spec, *_ in candidates]


# ---------------------------------------------------------------------
# Step 2: Ask LLM to generate a migrated snippet
# ---------------------------------------------------------------------

migrated_code = ask_llm(
    libo=OLD_LIB,
    libn=NEW_LIB,
    apio=TARGET_API,
    apins=apins,
    codeb=ORIGINAL_CODE,
    model=MODEL,
    engine=ENGINE,
    temperature=TEMPERATURE,
)


# ---------------------------------------------------------------------
# Step 3: Prepare AST information
# ---------------------------------------------------------------------

(
    OldTree,
    ParentO,
    OCNs,
    UnusedVarsO,
    UnAssignedVarsO,
    FuncDefsO,
) = preparation(ORIGINAL_CODE, [TARGET_API], OLD_LIB, NEW_LIB)

(NewTree, ParentN, _, _, _, _) = preparation(migrated_code, [], OLD_LIB, NEW_LIB)

OldTree1 = ast.parse(ORIGINAL_CODE)

history = {}


# ---------------------------------------------------------------------
# Step 4: Run migration synthesis
# ---------------------------------------------------------------------

migrated_tree = migrator(
    TARGET_API,
    OCNs,
    ParentN,
    ParentO,
    ast.parse(ORIGINAL_CODE),
    NewTree,
    OLD_LIB,
    NEW_LIB,
    history,
    FuncDefsO,
    None,
    CENs,
    OldTree1,
    ORIGINAL_CODE,
    migrated_code,
    get_apis("path", NEW_LIB),
)


# ---------------------------------------------------------------------
# Output result
# ---------------------------------------------------------------------

print(ast.unparse(migrated_tree))
