from scripts import check_numbers_sourced as cns
from scripts import claims_lint


def test_claims_lint_flags_forbidden():
    assert claims_lint.scan_text("This is guaranteed to work")
    assert claims_lint.scan_text("It is 100% accurate.")
    assert not claims_lint.scan_text("GRIDPRINT is not cryptographic proof.")
    assert not claims_lint.scan_text("A missing signal is never evidence of a fake.")


def test_numbers_sourced():
    assert cns.check_text("Coverage was 42.5% on the test set.") == [1]
    assert cns.check_text("Coverage was 42.5% <!-- src: results/eval/x/summary.json#coverage -->") == []
    assert cns.check_text("Lights flicker at 100 Hz on 50 Hz grids.") == []
    assert cns.check_text("Built with OpenCV 5.0.0 and Python 3.11.") == []
    assert cns.check_text("```\nspeed 3.2x\n```") == []
    assert cns.check_text("Speedup 1.4x") == [1]
