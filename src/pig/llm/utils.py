"""
LLM-related utility functions.
This includes functions for extracting relevant information from LLM responses.
"""

import ast

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


def show_prompt_and_query(prompt: str, query: str) -> None:
    """Displays the prompt and query sent to the LLM for debugging purposes.

    :param prompt: A prompt for the LLM.
    :type prompt: str
    :param query: A query for the LLM.
    :type query: str

    :return: None
    :rtype: None
    """
    console = Console()
    console.rule("[bold cyan]🚀 AskLLM Input[/bold cyan]")

    # Prompt 출력
    console.print(
        Panel.fit(
            Text(prompt, style="white"), title="[ Prompt ]", border_style="yellow"
        )
    )

    # Query 출력 (코드처럼 보이게)
    console.print(
        Panel.fit(
            Text(query, style="italic bright_white"),
            title="[ Query ]",
            border_style="bright_magenta",
        )
    )


def show_llm_response(response: str) -> None:
    """Displays the LLM response for debugging purposes.

    :param response: A response from the LLM.
    :type response: str

    :return: None
    :rtype: None
    """
    console = Console()
    console.rule("[bold green]💡 LLM Response[/bold green]")

    # LLM 응답 출력 (코드처럼 보이게)
    console.print(
        Panel.fit(
            Text(response, style="italic bright_white"),
            title="[ Response ]",
            border_style="green",
        )
    )


def is_valid_python_code(code: str) -> bool:
    """Checks if the provided code is valid Python code.

    :param code: The code snippet to be checked.
    :type code: str

    :return: True if the code is valid Python code, False otherwise.
    :rtype: bool
    """
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def fill_placeholders(block: str) -> str:
    """Fills placeholders in the code block with dummy values.

    :param block: The code block containing placeholders.
    :type block: str

    :return: The code block with placeholders filled.
    :rtype: str
    """
    code = ""

    for j in range(len(block.split("\n"))):
        line = block.split("\n")[j]

        if "unchanged" in line and "#" in line:
            code += line.replace("#", "pass #") + "\n"

        elif "existing" in line and "#" in line:
            code += line.replace("#", "pass #") + "\n"

        elif "code continues" in line and "#" in line:
            code += line.replace("#", "pass #") + "\n"

        elif "Do something" in line and "#" in line:
            code += line.replace("#", "pass #") + "\n"

        elif "..." in line:
            code += line.replace("...", "dummy_var") + "\n"

        else:
            code += line + "\n"

    return code.strip()


def find_code_blocks(answer: str) -> list[str]:
    """Finds all the code blocks from the LLM answer.

    :param answer: A response from the LLM.
    :type answer: str

    :return: A list of code blocks extracted from the answer.
    :rtype: list[str]

    """

    result = list()
    start = None

    for i in range(len(answer)):
        if (start == None) and (answer[i] == "`" and answer[i : i + 9] == "```python"):
            start = i + 9

        elif (start == None) and (answer[i] == "`" and answer[i : i + 3] == "```"):
            start = i + 2

        elif (start != None) and answer[i : i + 3] == "```":
            end = i
            result.append(fill_placeholders(answer[start:end].strip("`")))
            start = None

    if "```" not in answer:
        result.append(fill_placeholders(answer))

    return result


def extract_code(llm_answer: str, libo: str, libn: str) -> str:
    """Extracts the migrated code from the LLM answer.

    :param llm_answer: A response from the LLM.
    :type llm_answer: str
    :param libo: A name of the original library.
    :type libo: str
    :param libn: A name of the new library.
    :type libn: str

    :raises ValueError: If the extracted code is invalid or if multiple code blocks are found.

    :return: The extracted code.
    :rtype: str

    """
    # Find code blocks
    result = find_code_blocks(llm_answer)

    if len(result) == 1 and is_valid_python_code(result[0]):
        return result[0]

    else:
        raise ValueError(
            f"Multiple code blocks found for {libo} ({libn}). Please check the LLM response:\n{llm_answer}"
        )
