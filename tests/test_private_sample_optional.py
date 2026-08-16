"""Optional local smoke test for a private damaged document.

Set LEGACY_DOC_BAD_SAMPLE to a file path. No private fixture is committed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from legacy_doc_recover.recover import recover_file


@pytest.mark.skipif(not os.getenv("LEGACY_DOC_BAD_SAMPLE"), reason="private sample not configured")
def test_private_sample_structured_recovery():
    path = Path(os.environ["LEGACY_DOC_BAD_SAMPLE"])
    result = recover_file(path, allow_raw_fallback=False)
    assert result.success
    assert result.mode == "piece_table"
    assert len(result.text) > 0

