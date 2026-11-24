# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
class CuemsWsServerError(Exception):
    """Base exception for all cuems-editor errors.

    All other editor exceptions inherit from this class, so callers can
    catch ``CuemsWsServerError`` to handle any editor-originated failure.
    """


class FileIntegrityError(CuemsWsServerError):
    """Raised when an uploaded file's MD5 digest does not match the declared value.

    Example:
        >>> raise FileIntegrityError("MD5 mismatch: expected abc123, got def456")
    """


class NonExistentItemError(CuemsWsServerError):
    """Raised when a database lookup by UUID or unix_name returns no result.

    Example:
        >>> raise NonExistentItemError("item with uuid: 1234-... does not exist")
    """


class ExportError(CuemsWsServerError):
    """Raised when a project export is refused or cannot be completed.

    The ``str()`` is one line shown to the operator as it is: the exports
    folder or its apache conf is missing (E1), the disk would keep less than
    the reserve (E2), or a media file changed while it was zipped (E6).
    """


class NotTimeCodeError(CuemsWsServerError):
    """Raised when a string cannot be parsed as a valid CueMS timecode.

    Thrown by ``CuemsDBMedia.get_duration`` when ``ffprobe`` output does not
    match the ``HH:MM:SS.mmm`` pattern expected by ``CTimecode``.
    """


class EngineError(CuemsWsServerError):
    """Raised when ``cuems-engine`` returns a non-OK NNG IPC response.

    Also raised on timeout or connection failure.  The ``str()`` of the
    exception carries the engine's error value or the transport diagnostic.

    Example:
        >>> raise EngineError("Timeout: engine did not respond in 25s for project_load")
    """
