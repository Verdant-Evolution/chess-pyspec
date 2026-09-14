# SPEC scan-file cases

Each `*.spec` file in this directory is automatically tested by
`test/test_spec_file.py`. Add a JSON file with the same base name to state the
expected parser result. No test-code registration is needed.

The top-level JSON keys are:

- `scan_count`: number of scan blocks in the file.
- `number_of_scans`: optional value expected from `FileSpec.length`.
- `lookups`: optional scan-number lookups, each with `number`, an optional
  one-based `instance` (as in SPEC's `10.3` notation), and expected `command`.
- `scans`: one object per scan, in file order.

Within a scan object, `number` is required. Optional keys are `command`,
`order`, `number_in_file`, `source`, `file_epoch`, `columns`, `labels`,
`motor_names`, `motor_positions`, `data`, `count_time`, `errors`, and `mcas`.
Each MCA object can specify `calib`, `data`, and `calibrated_data`.

Use an empty list for `errors` when a fixture is valid and should not produce
parser errors.
