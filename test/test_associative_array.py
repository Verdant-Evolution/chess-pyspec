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


def test_decompose_key_parses_scalar_and_tuple_keys():
    assert AssociativeArray.decompose_key("3") == 3
    assert AssociativeArray.decompose_key("2.5") == 2.5
    assert AssociativeArray.decompose_key("hello") == "hello"

    v = (1, 2.5)
    assert AssociativeArray.decompose_key(AssociativeArray.compose_key(v)) == v


def test_try_parse_key_handles_numeric_and_string_values():
    assert AssociativeArray.try_parse_key("10") == 10
    assert AssociativeArray.try_parse_key("10.125") == 10.125
    assert AssociativeArray.try_parse_key("1e3") == 1000
    assert AssociativeArray.try_parse_key("not-a-number") == "not-a-number"


def test_iter_returns_decomposed_keys():
    arr = AssociativeArray()
    arr[1] = "one"
    arr["hello", 2] = "hello two"

    keys = list(arr)

    assert set(keys) == {1, ("hello", 2)}


def test_iterated_keys_can_directly_index_array():
    arr = AssociativeArray()
    arr[1] = "one"
    arr["hello", 2] = "hello two"
    arr[3.25] = "three point two five"

    values_by_key = {key: arr[key] for key in arr}

    assert values_by_key == {
        1: "one",
        ("hello", 2): "hello two",
        3.25: "three point two five",
    }


def test_to_dict_builds_nested_dict_for_two_dimensional_keys():
    arr = AssociativeArray()
    arr[1] = "one"
    arr["greeting", "en"] = "hello"
    arr["greeting", "es"] = "hola"

    assert arr.to_dict() == {
        1: "one",
        "greeting": {
            "en": "hello",
            "es": "hola",
        },
    }


def test_to_dict_raises_when_scalar_key_conflicts_with_subkeys():
    arr = AssociativeArray()
    arr["greeting"] = "hello"
    arr["greeting", "es"] = "hola"

    with pytest.raises(ValueError, match="already set to a non-dict value"):
        arr.to_dict()


def test_delete_scalar_key_then_reuse_for_depth_2_mapping():
    arr = AssociativeArray()
    arr["greeting"] = "hello"
    del arr["greeting"]

    arr["greeting", "es"] = "hola"
    arr["greeting", "en"] = "hello"

    assert arr["greeting", "es"] == "hola"
    assert arr["greeting", "en"] == "hello"


def test_to_dict_after_delete_then_depth_2_mapping():
    arr = AssociativeArray()
    arr["greeting"] = "hello"
    del arr["greeting"]

    arr["greeting", "es"] = "hola"

    assert arr.to_dict() == {
        "greeting": {
            "es": "hola",
        }
    }
