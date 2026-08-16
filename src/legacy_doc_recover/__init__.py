"""Best-effort text recovery from legacy Word binary .doc files."""

from .recover import RecoveryResult, recover_file, recover_bytes

__all__ = ["RecoveryResult", "recover_file", "recover_bytes"]
__version__ = "0.1.0"

