"""
Prompts for LLM queries in the PIG model."""


def generate_prompt(libo: str, libn: str) -> str:
    """Generates a prompt for migrating code between libraries.

    :param libo: A name of the original library.
    :type libo: str

    :param libn: A name of the new library.
    :type libn: str

    :return: The generated prompt.
    :rtype: str
    """

    INIT_PROMPT = f"""Python Library Migration Task
    You will be tasked with reimplementing a Python code snippet, migrating it from `{libo}` to `{libn}`.
──────────────────────────────────────────────
You are provided with a list of candidate APIs. While not all may be correct, the one ranked at the top is usually the most accurate match. Your task is to use the correct APIs from the list when they apply. If the listed APIs are incorrect or do not fulfill the described functionality, you should suggest and use more appropriate alternatives.
──────────────────────────────────────────────
📌 Code Migration Instructions:
- Replace each line of the original API usage with the selected API from the new library, line by line.
- Do not omit any migration lines, even if some lines are deleted during the rewrite.
- Ensure the final code is syntactically correct and free of errors.
- When using APIs, make sure to call them in the correct context.
- Consider the return values of the APIs.

📌 Migration Insight
- In most cases, the **input arguments do not change** between the original and target APIs.
- The migration should focus only on **replacing the API call**, not refactoring or transforming the logic, arguments, or output.
- You must **preserve all input arguments, their names, order, and types**, unless the new API strictly requires a change.
- Do not add, remove, reformat, or reinterpret arguments unless it is essential for compatibility with the new API.

──────────────────────────────────────────────
Important Notes:

- Use the provided candidate APIs unless none are appropriate.
- Some candidate APIs may be weak matches (e.g., similar syntax but different purpose).
- Use any supported arguments from the selected API that help preserve the original behavior.

Your response must include only the **full migrated code**.
No explanations, comments, or additional text.

Example input code when migrating from `oldlib` to `newlib`, and the API to be replaced is `compute`:
>>> Example Input
# original
```python
result = oldlib.compute(data, normalize=True)
```

Example output when migrating from `oldlib` to `newlib`, and the API to be replaced is `compute`:

>>> Example Output
```python
import newlib
def A():
    data = [1, 2, 3, 4, 5]
    result = newlib.calculate(data, normalize=True)
```"""

    return INIT_PROMPT


def generate_query(
    libo: str,
    libn: str,
    apio: str,
    cand_apis: str,
    codeb: str,
) -> str:
    """Generates a query for migrating code between libraries.

    :param libo: A name of the original library.
    :type libo: str
    :param libn: A name of the new library.
    :type libn: str
    :param apio: A name of the original API to be replaced.
    :type apio: str
    :param cand_apis: A formatted string of candidate APIs.
    :type cand_apis: str
    :param codeb: The code snippet to be migrated.
    :type codeb: str

    :return: The generated query.
    :rtype: str
    """

    QUERY = f"""Migrate the following Python code snippet from the `{libo}` library to the `{libn}` library.\nBelow are the candidate APIs that may serve as replacements for `{apio}`, listed in ascending order of relevance:

{cand_apis}

Here is the code snippet to be migrated:

```python
{codeb}```"""

    return QUERY
