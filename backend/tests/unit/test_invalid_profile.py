"""Each invalid-profile fixture, run through the real validator, must
surface exactly its own labeled defect — proving the generator's invalid
bundles and the validator's checks agree with each other.
"""

from datetime import date

import pytest

from revenueflowai.ingestion.validator import validate_bundle
from revenueflowai.seed.invalid import FIXTURES, generate_invalid_bundles

AS_OF = date(2026, 10, 2)


@pytest.fixture(scope="module")
def invalid_bundles(tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("invalid")
    manifest = generate_invalid_bundles(seed=42, as_of=AS_OF, output_dir=out_dir)
    return out_dir, manifest


def test_every_fixture_is_generated(invalid_bundles):
    _out_dir, manifest = invalid_bundles
    assert set(manifest.keys()) == {f.name for f in FIXTURES}


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.name)
def test_fixture_surfaces_its_labeled_defect(invalid_bundles, fixture):
    out_dir, _manifest = invalid_bundles
    result = validate_bundle(out_dir / fixture.name)

    if fixture.expected_error_code is None:
        # Expected to pass ingestion (e.g. formula-bearing text is valid
        # data; the requirement is safe export escaping, not rejection).
        assert result.is_valid, [e.message for e in result.errors]
    else:
        assert any(e.code == fixture.expected_error_code for e in result.errors), (
            f"Expected error code {fixture.expected_error_code!r} not found; got "
            f"{[e.code for e in result.errors]}"
        )
