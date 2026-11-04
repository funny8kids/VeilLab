from __future__ import annotations

import re

MOCK_VERIFIER_NAME = "MOCK_VERIFIER"
_PROOF_RE = re.compile(r"^0x[0-9a-fA-F]+$")


class MockVerifier:
    """Shape-only verifier used by the local demo.

    This performs **no cryptographic verification**. It is clearly labelled in
    every submission response and must never be used with real value.
    """

    name = MOCK_VERIFIER_NAME

    @staticmethod
    def verify(proof: str) -> bool:
        if not isinstance(proof, str) or not _PROOF_RE.match(proof):
            return False
        hex_digits = len(proof) - 2
        return 64 <= hex_digits <= 4096 and hex_digits % 2 == 0
