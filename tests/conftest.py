from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def mixed_mbox() -> Path:
    return FIXTURES / "mixed.mbox"
