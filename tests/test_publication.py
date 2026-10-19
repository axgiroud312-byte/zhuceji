from pathlib import Path

import pytest

from agnes_provisioner.cli import parser


def test_bulk_prepare_requires_explicit_private_inputs():
    with pytest.raises(SystemExit) as error:
        parser().parse_args(["bulk", "prepare"])
    assert error.value.code == 2


def test_bulk_prepare_accepts_explicit_inputs_without_implicit_legacy_database():
    args = parser().parse_args([
        "bulk", "prepare", "--source", "approved.txt", "--sample", "sample",
        "--report", "report.json",
    ])
    assert args.source == Path("approved.txt")
    assert args.sample == Path("sample")
    assert args.report == Path("report.json")
    assert args.legacy is None
