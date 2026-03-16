"Functions to map similar APIs based on signature information."

from pathlib import Path
from typing import Union
from itertools import product
from difflib import SequenceMatcher

from . import api_lst


def compute_greedy_arg_mapping(argso: set, argsn: set, libo: str, libn: str) -> float:
    """Computes an argument similarity score between two sets of arguments using a greedy matching algorithm.

    :param argso: A set of arguments from the original API.
    :type argso: set
    :param argsn: A set of arguments from the new API.
    :type argsn: set
    :param libo: A name of the original library.
    :type libo: str
    :param libn: A name of the new library.
    :type libn: str

    :return: A normalized similarity score between the two argument sets.
    :rtype: float
    """

    # Step 1: Compute all possible similarities
    all_pairs = [
        (a, b, compute_string_similarity(a, b, libo, libn))
        for a, b in product(argso, argsn)
    ]

    # Step 2: Sort by descending similarityclear
    sorted_pairs = sorted(all_pairs, key=lambda x: x[2], reverse=True)

    matched_a = set()
    matched_b = set()
    final_matches = []

    # Step 3: Greedy match
    for a, b, score in sorted_pairs:
        if a not in matched_a and b not in matched_b:
            final_matches.append((a, b, score))
            matched_a.add(a)
            matched_b.add(b)

    # Step 4: Normalize by number of matches (not argument list lengths)
    if final_matches:
        total_score = sum(score for _, _, score in final_matches)
        max_arg_num = max(len(argso), len(argsn))
        normalized_score = total_score / (max_arg_num - len(final_matches) + 1) ** (
            1 / 2
        )

    else:
        normalized_score = 0.0

    return normalized_score


def compute_string_similarity(word0: str, word1: str, libo: str, libn: str) -> float:
    """Computes a similarity score between two strings, considering special case.

    ":param word1: The first string to compare.
    :type word1: str
    :param word2: The second string to compare.
    :type word2: str
    :param libo: A name of the original library.
    :type libo: str
    :param libn: A name of the new library.
    :type libn: str

    :return: A similarity score between the two strings.
    :rtype: float
    """

    # SHOULD BE BOTH UPPER CASE
    if (word0.isupper() and word1.islower()) or (word0.islower() and word1.isupper()):
        return 0

    if word0.lower() == word1.lower() or (
        word0.lower() == libo.lower() and word1.lower() == libn.lower()
    ):

        return 1

    sim1 = SequenceMatcher(None, word0.lower(), word1.lower()).ratio()
    sim2 = SequenceMatcher(None, word1.lower(), word0.lower()).ratio()

    return max(sim1, sim2)


def api_mapping(
    apios: list[str],
    libo: str,
    libn: str,
    libn_path: Union[str, Path],
    argso: list,
    top: int = -1,
) -> dict[str : set[tuple[str, tuple, float, float, str]]]:
    """Maps APIs from the original library to candidate APIs in the new library based on name and argument similarity.

    :param apios: A list of original API names.
    :type apios: list[str]

    :param libo: A name of the original library.
    :type libo: str

    :param libn: A name of the new library.
    :type libn: str

    :param libn_path: A path to the new library.
    :type libn_path: Union[str, Path]

    :param argso: A list of arguments from the original API.
    :type argso: list

    :param top: An integer specifying the number of top candidates to return. Defaults to -1 (all candidates).
    :type top: int, optional

    :return: A dictionary mapping original APIs to candidate APIs with similarity scores. A key is an original API name, and a value is a set of tuples containing candidate API name, signature, name similarity score, argument similarity score, and file path.
    :rtype: dict[str : set[tuple[str, tuple, float, float, str]]]
    """

    mapping = dict()
    apins = api_lst.extract_apis(libn, libn_path)

    for apio in apios:
        history = set()

        for path, val in apins.items():
            for i in range(len(val)):
                for apin, argsn in val[i]:
                    # Compute name similarity between original API and new API
                    name_similarity = compute_string_similarity(apio, apin, libo, libn)

                    if not isinstance(argsn, list):
                        argsn = argsn[0]

                    # Compute argument similarity between original API and new API
                    if len(argso) == 0 and len(argsn) == 0:
                        arg_similarity = 1

                    else:
                        argso = set(argso) - {"self", "args", "kwargs"}
                        argsn = set(argsn) - {"self", "args", "kwargs"}

                        arg_similarity = compute_greedy_arg_mapping(
                            argso, argsn, libo, libn
                        )

                    history.add(
                        (
                            apin,
                            tuple(set(sign)),
                            name_similarity,
                            arg_similarity,
                            path,
                        )
                    )

        history = sorted(history, key=lambda x: (x[2], x[3]), reverse=True)

        real_cands = set()

        for apin, sign, name_score, arg_score, path in history:
            if (apin, sign, name_score, arg_score, path) in real_cands:
                continue

            # Now, set remembers the order of insertion
            real_cands.add((apin, sign, name_score, arg_score, path))

            if len(real_cands) == top and top != -1:
                break

        mapping[apio] = real_cands

    return mapping
