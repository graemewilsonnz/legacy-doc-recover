class RecoveryError(Exception):
    """Base exception for expected recovery failures."""


class CFBError(RecoveryError):
    """Raised when the Compound File Binary container cannot be interpreted."""


class DocFormatError(RecoveryError):
    """Raised when Word binary structures cannot be interpreted."""


class UnsupportedDocError(RecoveryError):
    """Raised for a recognised but intentionally unsupported document feature."""

