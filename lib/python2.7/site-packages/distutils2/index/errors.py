"""distutils2.pypi.errors

All errors and exceptions raised by PyPiIndex classes.
"""
from distutils2.errors import DistutilsIndexError


class ProjectNotFound(DistutilsIndexError):
    """Project has not been found"""


class DistributionNotFound(DistutilsIndexError):
    """The release has not been found"""


class ReleaseNotFound(DistutilsIndexError):
    """The release has not been found"""


class CantParseArchiveName(DistutilsIndexError):
    """An archive name can't be parsed to find distribution name and version"""


class DownloadError(DistutilsIndexError):
    """An error has occurs while downloading"""


class HashDoesNotMatch(DownloadError):
    """Compared hashes does not match"""


class UnsupportedHashName(DistutilsIndexError):
    """A unsupported hashname has been used"""


class UnableToDownload(DistutilsIndexError):
    """All mirrors have been tried, without success"""


class InvalidSearchField(DistutilsIndexError):
    """An invalid search field has been used"""
