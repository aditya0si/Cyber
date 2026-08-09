"""Phase 0 smoke test (docs/19).

Later phases add unit/integration/replay/golden suites under tests/.
"""

from cybersim import __version__


def test_version_importable() -> None:
    assert isinstance(__version__, str)
    assert __version__.count(".") >= 1
