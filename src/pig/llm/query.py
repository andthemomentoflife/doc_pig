"""
Module for querying the LLM with specific prompts and parameters.
"""

import os
import openai
from ollama import Client
from typing import Union

from .utils import *
from .prompts import *

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:8000")


def ask_llm(
    libo: str,
    libn: str,
    apio: str,
    apins: list[tuple[str, str]],  # List of Candidate (API name, spec)
    codeb: str,
    model: str,
    engine: str,  # 'openai' | 'ollama'
    temperature: Union[float, int] = 1,
) -> str:
    """Queries the LLM with the constructed prompt and returns the response.

    :param libo: A name of the original library.
    :type libo: str
    :param libn: A name of the new library.
    :type libn: str
    :param apio: A name of the original API to be replaced.
    :type apio: str
    :param apins: A list of candidate APIs for replacement.
    :type apins: list[tuple[str, str]]
    :param codeb: The code snippet to be migrated.
    :type codeb: str
    :param model: A name of the LLM model to use.
    :type model: str
    :param engine: An engine to use ('openai' or 'ollama').
    :type engine: str
    :param temperature: A value that controls the randomness of the output. Defaults to 1.
    :type temperature: Union[float, int], optional

    :raises ValueError: If an unsupported engine is specified.

    :return: The generated query.
    :rtype: str
    """

    def format_new_apis(apins: list[tuple[str, str]]) -> str:
        formatted = ""
        for api_name, api_spec in apins:
            formatted += f"- {api_name}: {api_spec}\n"
        return formatted.strip()

    PROMPT = generate_prompt(libo, libn)
    QUERY = generate_query(libo, libn, apio, format_new_apis(apins), codeb)

    print("Setting")
    print("Engine:", engine)
    print("Model:", model)
    print("Temperature:", temperature)

    show_prompt_and_query(PROMPT, QUERY)

    if engine == "openai":
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": QUERY},
        ]

        _response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        response = _response["choices"][0]["message"]["content"]

    elif engine == "ollama":
        client = Client(host=OLLAMA_HOST)
        client.pull(model=model)
        _response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": QUERY},
            ],
            options={
                "num_ctx": 4096,
                "temperature": temperature,
            },
        )

        response = _response["message"]["content"]

    else:
        raise ValueError("Unsupported engine. Choose 'openai' or 'ollama'.")

    show_llm_response(response)
    result = find_code_blocks(response)[0]

    return result
