def update_dict(dict1: dict, dict2: dict) -> dict:
    """Updates original dictionary with values from another dictionary by summing corresponding tuple elements.
    :param dict1: The original dictionary to be updated.
    :type dict1: dict

    :param dict2: The dictionary with values to add to the original dictionary.
    :type dict2: dict

    :return: The updated original dictionary with summed tuple values.
    :rtype: dict
    """

    for key, val in dict2.items():
        v1, v2, v3, v4, v5 = val

        if key in dict1:
            dict1[key] = (
                dict1[key][0] + v1,
                dict1[key][1] + v2,
                dict1[key][2] + v3,
                dict1[key][3] + v4,
                dict1[key][4] + v5,
            )

        if key not in dict1:
            dict1[key] = (v1, v2, v3, v4, v5)

    return dict1
