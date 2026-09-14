"""Data-driven conformance tests for the SPEC scan-file reader.

Each ``test/spec_cases/*.spec`` file is a scan-file fixture.  Its matching JSON
file describes only the properties relevant to that case.  The parametrization
below discovers every fixture automatically, so a new case requires no Python
changes.
"""

import json
from pathlib import Path

import numpy
import pytest

from pyspec.file.spec import FileSpec


CASE_DIRECTORY = Path(__file__).with_name("spec_cases")
CASE_FILES = sorted(CASE_DIRECTORY.glob("*.spec"))


def load_case_expectations(spec_file):
    expectation_file = spec_file.with_suffix(".json")
    assert expectation_file.is_file(), (
        f"Missing expectations for {spec_file.name}; "
        f"add {expectation_file.name} alongside the fixture."
    )
    return json.loads(expectation_file.read_text())


@pytest.mark.parametrize("spec_file", CASE_FILES, ids=lambda path: path.stem)
def test_spec_file_cases(spec_file):
    expected = load_case_expectations(spec_file)
    spec_file_data = FileSpec(spec_file)

    assert len(spec_file_data) == expected["scan_count"]
    assert spec_file_data.length == expected.get("number_of_scans", expected["scan_count"])

    for lookup in expected.get("lookups", []):
        if "instance" in lookup:
            scan = spec_file_data.getScanByNumber(
                lookup["number"], lookup["instance"]
            )
        else:
            scan = spec_file_data.getScanByNumber(lookup["number"])
        assert scan is not None
        assert scan.command == lookup["command"]

    assert len(spec_file_data) == len(expected["scans"])
    for scan, scan_expected in zip(spec_file_data, expected["scans"]):
        assert scan.number == scan_expected["number"]
        assert scan.command == scan_expected.get("command", "")
        assert scan.order == scan_expected.get("order", scan.order)
        assert scan.getNumberInFile() == scan_expected.get(
            "number_in_file", scan.getNumberInFile()
        )

        if "source" in scan_expected:
            assert scan.source == scan_expected["source"]
        if "file_epoch" in scan_expected:
            assert scan.file_epoch == scan_expected["file_epoch"]
        if "columns" in scan_expected:
            assert scan.nb_columns == scan_expected["columns"]
        if "labels" in scan_expected:
            assert scan.labels == scan_expected["labels"]
        if "motor_names" in scan_expected:
            assert scan.motor_names == scan_expected["motor_names"]
        if "motor_positions" in scan_expected:
            assert [list(position) for position in scan.motor_positions] == scan_expected[
                "motor_positions"
            ]
        if "data" in scan_expected:
            numpy.testing.assert_allclose(scan.data, scan_expected["data"])
        if "count_time" in scan_expected:
            assert scan.count_time == scan_expected["count_time"]
        if "errors" in scan_expected:
            assert scan.metadata["errors"] == scan_expected["errors"]

        expected_mcas = scan_expected.get("mcas", [])
        assert scan.nb_mcas == len(expected_mcas)
        for mca, mca_expected in zip(scan.mcas, expected_mcas):
            if "calib" in mca_expected:
                assert mca.calib == mca_expected["calib"]
            if "data" in mca_expected:
                numpy.testing.assert_allclose(mca.data, mca_expected["data"])
            if "calibrated_data" in mca_expected:
                numpy.testing.assert_allclose(
                    mca.getData(calibrated=True), mca_expected["calibrated_data"]
                )
