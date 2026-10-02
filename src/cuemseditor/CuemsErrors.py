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


class DocumentLoadFailed(CuemsWsServerError):
    """The library refused to open a project's script: an unrepairable value,
    or a document newer than the library.

    Raised by ``CuemsDBProject.open`` around the library's ``ValidationError``
    (not ``SchemaError``), so the session can answer ``document_load_failed``
    with the path the library read.

    Attributes:
        document: Path of the script file.
        cause: The library's ``ValidationError``; ``cause.violation`` (when
            present) carries ``location == (cue_id, field)``.
    """

    def __init__(self, document, cause):
        super().__init__(str(cause))
        self.document = document
        self.cause = cause


class OriginalNotPreserved(CuemsWsServerError):
    """The pre-repair script could not be moved into the trash, so it was not
    overwritten.

    Raised by ``CuemsDBProject.update`` before ``CuemsScript.save`` is called.
    """
