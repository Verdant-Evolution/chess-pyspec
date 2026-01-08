from typing import Any, Mapping
from pyspec._connection.associative_array import (
    AssociativeArray,
    AssociativeArrayElement,
    get_associative_array_key,
    pack_associative_array_element,
    unpack_associative_array_element,
)
import pytest


def test_key_parsing():
    assert get_associative_array_key("../x") is None
    assert get_associative_array_key("../x[1]") == ("1", "")
    assert get_associative_array_key("../x[1][2]") == ("1", "2")
    assert get_associative_array_key("../x[hello][goodbye]") == ("hello", "goodbye")


def test_unpack():
    arr = AssociativeArray()
    arr["1"] = "one"
    assert unpack_associative_array_element("../x[1]", arr) == "one"
    assert unpack_associative_array_element("../x", arr) == arr


def compare_array(arr1: AssociativeArray, arr2: AssociativeArray) -> bool:
    if set(arr1.data.keys()) != set(arr2.data.keys()):
        return False
    for key in arr1.data.keys():
        if arr1.data[key] != arr2.data[key]:
            return False
    return True


def test_pack():
    a1 = AssociativeArray()
    a1["1"] = "one"
    assert compare_array(
        pack_associative_array_element("../x[1]", "one"),  # type: ignore
        a1,
    )
    a2 = AssociativeArray()
    a2[1, 2] = "one two"
    assert compare_array(
        pack_associative_array_element("../x[1][2]", "one two"),  # type: ignore
        a2,
    )
    assert pack_associative_array_element("../x", "value") == "value"


def test_deleted():
    arr = AssociativeArray()
    arr["1"] = "one"
    arr["2"] = "two"
    arr["3"] = "three"
    del arr["2"]

    with pytest.raises(KeyError):
        arr["2"]

    arr[1]
    arr[3]
