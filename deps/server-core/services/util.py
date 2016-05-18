# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Sync Server
#
# The Initial Developer of the Original Code is the Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#   Toby Elliott (telliott@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
"""
Various utilities
"""
import sys
import traceback
import random
import string
from hashlib import sha256, sha1, md5
import base64
import simplejson as json
import itertools
import re
import datetime
import os
import urllib2
from decimal import Decimal, InvalidOperation
import time
import warnings

from webob.exc import HTTPBadRequest, HTTPServiceUnavailable
from webob import Response

import scrypt

import sqlalchemy
from sqlalchemy.exc import DBAPIError, OperationalError, TimeoutError

from metlog.holder import CLIENT_HOLDER
from services.exceptions import BackendError, BackendTimeoutError  # NOQA

random.seed()
_RE_CODE = re.compile('[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}')


def function_moved(moved_to, follow_redirect=True):
    """This is a decorator that will emit a warning that a function has been
    moved elsewhere

    Arguments:
        moved_to: the string representing the new function name
        follow_redirect: if true, attempts to resolve the function specified in
        moved_to and calls that instead of the original function
    """
    def arg_wrapper(func):
        def moved_function(*args, **kwargs):
            from services.pluginreg import _resolve_name
            warnings.warn("%s has moved to %s" % (func.__name__, moved_to),
                          category=DeprecationWarning, stacklevel=2)
            if follow_redirect:
                new_func = _resolve_name(moved_to)
                return new_func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        return moved_function
    return arg_wrapper


def randchar(chars=string.digits + string.letters):
    """Generates a random char using urandom.

    If the system does not support it, the function fallbacks on random.choice

    See Haypo's explanation on the used formula to pick a char:
    http://bitbucket.org/haypo/hasard/src/tip/doc/common_errors.rst
    """
    try:
        pos = int(float(ord(os.urandom(1))) * 256. / 255.)
        return chars[pos % len(chars)]
    except NotImplementedError:
        return random.choice(chars)


def time2bigint(value):
    """Encodes a float timestamp into a big int"""
    return int(value * 100)


def bigint2time(value, precision=2):
    """Decodes a big int into a timestamp.

    The returned timestamp is a 2 digits Decimal.
    """
    if value is None:   # unexistant
        return None
    res = Decimal(value) / 100
    digits = '0' * precision
    return res.quantize(Decimal('1.' + digits))


def round_time(value=None, precision=2):
    """Transforms a timestamp into a two digits Decimal.

    Arg:
        value: timestamps representation - float or str.
        If None, uses time.time()

        precision: number of digits to keep. defaults to 2.

    Return:
        A Decimal two-digits instance.
    """
    if value is None:
        value = time.time()
    if not isinstance(value, str):
        value = str(value)
    try:
        digits = '0' * precision
        return Decimal(value).quantize(Decimal('1.' + digits))
    except InvalidOperation:
        raise ValueError(value)


_SALT_LEN = 8


def _gensalt():
    """Generates a salt"""
    return ''.join([randchar() for i in range(_SALT_LEN)])


def ssha(password, salt=None):
    """Returns a Salted-SHA password

    Args:
        password: password
        salt: salt to use. If none, one is generated
    """
    password = password.encode('utf8')
    if salt is None:
        salt = _gensalt()
    ssha = base64.b64encode(sha1(password + salt).digest()
                               + salt).strip()
    return "{SSHA}%s" % ssha


def ssha256(password, salt=None):
    """Returns a Salted-SHA256 password

    Args:
        password: password
        salt: salt to use. If none, one is generated

    """
    password = password.encode('utf8')
    if salt is None:
        salt = _gensalt()
    ssha = base64.b64encode(sha256(password + salt).digest()
                               + salt).strip()
    return "{SSHA-256}%s" % ssha


def sscrypt(password, salt=None):
    """Returns a Salted-Scrypt password hash

    Args:
        password: password
        salt: salt to use. If none, one is generated

    """
    password = password.encode('utf8')
    if salt is None:
        salt = _gensalt()
    sscrypt = base64.b64encode(scrypt.hash(password, salt) + salt).strip()
    return "{SSCRYPT}%s" % sscrypt


def validate_password(clear, hash):
    """Validates a Salted-SHA(256) password

    Args:
        clear: password in clear text
        hash: hash of the password
    """
    if hash.startswith('{SSCRYPT}'):
        real_hash = hash.split('{SSCRYPT}')[-1]
        hash_meth = sscrypt
    elif hash.startswith('{SSHA-256}'):
        real_hash = hash.split('{SSHA-256}')[-1]
        hash_meth = ssha256
    else:
        real_hash = hash.split('{SSHA}')[-1]
        hash_meth = ssha

    salt = base64.decodestring(real_hash)[-_SALT_LEN:]

    # both hash_meth take a unicode value for clear
    password = hash_meth(clear, salt)
    return password == hash


def valid_password(user_name, password):
    """Checks a password strength.

    Args:
        user_name: user name associated with the password
        password: password

    Returns:
        True or False
    """
    if password is None:
        return False

    password = password.encode('utf8')

    if len(password) < 8:
        return False

    user_name = user_name.encode('utf8')
    return user_name.lower().strip() != password.lower().strip()


def batch(iterable, size=100):
    """Returns the given iterable split into batches, of size."""
    counter = itertools.count()

    def ticker(key):
        return next(counter) // size

    for key, group in itertools.groupby(iter(iterable), ticker):
        yield group


class HTTPJsonBadRequest(HTTPBadRequest):
    """Allow WebOb Exception to hold Json responses.

    XXX Should be fixed in WebOb
    """
    def generate_response(self, environ, start_response):
        if self.content_length is not None:
            del self.content_length

        headerlist = [(key, value) for key, value in
                      list(self.headerlist)
                      if key != 'Content-Type']
        body = json.dumps(self.detail, use_decimal=True)
        resp = Response(body,
            status=self.status,
            headerlist=headerlist,
            content_type='application/json')
        return resp(environ, start_response)


class HTTPJsonServiceUnavailable(HTTPServiceUnavailable):
    """Allow WebOb Exception to hold Json responses.

    XXX Should be fixed in WebOb
    """
    def generate_response(self, environ, start_response):
        if self.content_length is not None:
            del self.content_length
        self.headers['Content-Type'] = 'application/json'
        body = json.dumps(self.detail, use_decimal=True)
        resp = Response(body,
            status=self.status,
            headerlist=self.headers.items())
        return resp(environ, start_response)


def email_to_idn(addr):
    """ Convert an UTF-8 encoded email address to it's IDN (punycode)
        equivalent

        this method can raise the following:
        UnicodeError -- the passed string is not Unicode valid or BIDI
        compliant
          Be sure to examine the exception cause to determine the final error.
    """
    # decode the string if passed as MIME (some MIME encodes @)
    addr = urllib2.unquote(addr).decode('utf-8')
    if '@' not in addr:
        return addr
    prefix, suffix = addr.split('@', 1)
    return "%s@%s" % (prefix.encode('idna'), suffix.encode('idna'))


class CatchErrorMiddleware(object):
    """Middleware that catches error, log them and return a 500"""
    def __init__(self, app, logger_name='root', hook=None,
                 type='application/json'):
        self.app = app
        self.logger = CLIENT_HOLDER.default_client
        self.hook = hook
        self.ctype = type

    def __call__(self, environ, start_response):
        try:
            return self.app(environ, start_response)
        except:
            # We don't want to write arbitrary user-provided data into the
            # the logfiles.  For example, the sort of data that might show
            # up in the payload of a ValueError exception.
            # Format the traceback using standard printing, but use repr()
            # on the exception value itself to avoid this issue.
            exc_type, exc_val, exc_tb = sys.exc_info()
            lines = ["Uncaught exception while processing request:\n"]
            req_method = environ.get("REQUEST_METHOD", "")
            req_path = environ.get("SCRIPT_NAME", "")
            req_path += environ.get("PATH_INFO", "")
            lines.append("%s %s\n" % (req_method, req_path))
            lines.extend(traceback.format_tb(exc_tb))
            lines.append("%r\n" % (exc_type,))
            lines.append("%r\n" % (exc_val,))
            err = "".join(lines)
            # Log it, then send a crash id back to the client.
            hash = create_hash(err)
            self.logger.error(hash)
            self.logger.error(err)
            start_response('500 Internal Server Error',
                           [('content-type', self.ctype)])

            response = json.dumps("application error: crash id %s" % hash)
            if self.hook:
                try:
                    response = self.hook({'error': err, 'crash_id': hash,
                                          'environ': environ})
                except TypeError:
                    # try the old way
                    msg = ("hooks now receive a dict containing information "
                           "about the error")
                    warnings.warn(msg, DeprecationWarning, stacklevel=2)
                    response = self.hook()
                except Exception:
                    pass

            return [response]


def create_engine(*args, **kwds):
    """Wrapper for sqlalchemy.create_engine with some extra security measures.

    This function wraps a call to sqlalchemy.create_engine with logic to
    restrict the process umask.  This ensures that sqlite database files are
    created with secure permissions by default.
    """
    old_umask = os.umask(0077)
    try:
        return sqlalchemy.create_engine(*args, **kwds)
    finally:
        os.umask(old_umask)


def execute_with_cleanup(engine, query, *args, **kwargs):
    """Execution wrapper that kills queries on untimely exit.

    This is a simple wrapper for engine.execute() that will clean up any
    running queries if the execution is interrupted by a control-flow
    exception such as KeyboardInterrupt or gevent.Timeout.

    The cleanup currently works only for the PyMySQL driver.  Other drivers
    will still work, they just won't get the cleanup.
    """
    conn = engine.contextual_connect(close_with_result=True)
    try:
        return conn.execute(query, *args, **kwargs)
    except Exception:
        # Normal exceptions are passed straight through.
        raise
    except BaseException:
        # Control-flow exceptions trigger the cleanup logic.
        exc, val, tb = sys.exc_info()
        logger = CLIENT_HOLDER.default_client
        logger.debug("query was interrupted by %s", val)
        try:
            # Only cleanup SELECT, INSERT or UPDATE statements.
            # There are concerns that rolling back DELETEs is too costly.
            # XXX TODO: won't work if we prepend a comment to the queries.
            query_str = str(query).upper()
            if not query_str.startswith("SELECT "):
                if not query_str.startswith("INSERT "):
                    if not query_str.startswith("UPDATE "):
                        msg = "  refusing to kill unsafe query: %s"
                        logger.debug(msg, query_str[:100])
                        raise
            # The KILL command is specific to MySQL, and this method of getting
            # the threadid is specific to the PyMySQL driver.  Other drivers
            # will cause an AttributeError, failing through to the "finally"
            # clause at the end of this block.
            thread_id = conn.connection.server_thread_id[0]
            logger.debug("  killing connection %d", thread_id)
            cleanup_query = "KILL %d" % (thread_id,)
            # Use a freshly-created connection so that we don't block waiting
            # for something from the pool.  Unfortunately this requires use of
            # a private API and raw cursor access.
            cleanup_conn = engine.pool._create_connection()
            try:
                cleanup_cursor = cleanup_conn.connection.cursor()
                try:
                    cleanup_cursor.execute(cleanup_query)
                    logger.debug("  successfully killed %d", thread_id)
                except Exception:
                    logger.exception("  failed to kill %d", thread_id)
                    raise
                finally:
                    cleanup_cursor.close()
            finally:
                cleanup_conn.close()
        finally:
            try:
                # Don't return this connection to the pool.
                conn.invalidate()
            finally:
                # Always re-raise the original error.
                raise exc, val, tb


def safe_execute(engine, *args, **kwargs):
    """Execution wrapper that will raise a HTTPServiceUnavailableError
    on any OperationalError errors and log it.
    """
    try:
        # It's possible for the backend to raise a "connection invalided" error
        # if e.g. the server timed out the connection.  SQLAlchemy purges the
        # the whole connection pool if this happens, so one retry is enough.
        try:
            return execute_with_cleanup(engine, *args, **kwargs)
        except DBAPIError, exc:
            if _is_retryable_db_error(engine, exc):
                logger = CLIENT_HOLDER.default_client
                logger.incr('services.util.safe_execute.retry')
                logger.debug('retrying due to db error %r', exc)
                return execute_with_cleanup(engine, *args, **kwargs)
            else:
                raise
    except Exception, exc:
        if not _is_operational_db_error(engine, exc):
            raise
        err = traceback.format_exc()
        logger = CLIENT_HOLDER.default_client
        logger.error(err)
        # Due to an apparent bug in SQLAlchemy, it's possible for some kinds
        # of connection failure to leave zombies checked out of the pool.
        # Ref:  http://www.sqlalchemy.org/trac/ticket/2695
        # We employ a rather brutal workaround: re-create the entire pool.
        if _get_mysql_error_code(engine, exc) in (2006, 2013, 2014):
            if not exc.connection_invalidated:
                engine.dispose()
        raise BackendError(str(exc))


def _get_mysql_error_code(engine, exc):
    """Try to get the MySQL error code associated with a db exception.

    If the code can be determined then it is returned as an integer.  If
    not (say, if the database is not mysql) then None is returned.
    """
    # Unfortunately this requires use of a private API.
    # The try-except will also catch cases where we're not running MySQL.
    try:
        return engine.dialect._extract_error_code(exc.orig)
    except AttributeError:
        return None


def _is_retryable_db_error(engine, exc):
    """Check whether we can safely retry in response to the given db error."""
    # Any connection-related errors can be safely retried.
    if exc.connection_invalidated:
        return True
    # MySQL Lock Wait Timeout errors can be safely retried.
    mysql_error_code = _get_mysql_error_code(engine, exc.orig)
    if mysql_error_code == 1205:
        return True
    # Any other error is assumed not to be retryable.  Better safe than sorry.
    return False


def _is_operational_db_error(engine, exc):
    """Check whether the given error is an operations-related db error.

    An operations-related error is loosely defined as something caused by
    the operational environment, e.g. the database being overloaded or
    unreachable.  It doesn't represent a bug in the code.
    """
    # All OperationalError or TimeoutError instances are operational.
    if isinstance(exc, (OperationalError, TimeoutError)):
        return True
    # Only some DBAPIError instances are operational.
    if isinstance(exc, DBAPIError):
        mysql_error_code = _get_mysql_error_code(engine, exc.orig)
        # Any retryable error is operational.
        if _is_retryable_db_error(engine, exc):
            return True
        # MySQL "Query execution was interrupted" errors are operational.
        # They're produced by ops killing long-running queries.
        if mysql_error_code == 1317:
            return True
    # Everything else counts as a programming error.
    return False


def get_source_ip(environ):
    """Extracts the source IP from the environ."""
    if 'HTTP_X_FORWARDED_FOR' in environ:
        return environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    elif 'REMOTE_ADDR' in environ:
        return environ['REMOTE_ADDR']
    return None


def create_hash(data):
    """Creates a unique hash using the data provided
    and a bit of randomness
    """
    rand = ''.join([randchar() for x in range(10)])
    data += rand
    return md5(data + rand).hexdigest()


@function_moved('services.user.extract_username')
def extract_username(username):
    pass


@function_moved('services.formatters.text_response')
def text_response(data, **kw):
    pass


@function_moved('services.formatters.json_response')
def json_response(data, **kw):
    pass


@function_moved('services.formatters.html_response')
def html_response(data, **kw):
    pass


@function_moved('services.formatters.newlines_response')
def newlines_response(lines, **kw):
    pass


@function_moved('services.formatters.whoisi_response')
def whoisi_response(lines, **kw):
    pass


@function_moved('services.formatters.convert_response')
def convert_response(request, lines, **kw):
    pass


@function_moved('services.http_helpers.get_url')
def get_url(url, method='GET', data=None, user=None, password=None, timeout=5,
            get_body=True, extra_headers=None):
    pass


@function_moved('services.http_helpers.proxy')
def proxy(request, scheme, netloc, timeout=5):
    pass


@function_moved('services.resetcodes.ResetCode._generate_reset_code', False)
def generate_reset_code():
    """Generates a reset code

    Returns:
        reset code, expiration date
    """
    from services.resetcodes import ResetCode
    rc = ResetCode()

    code = rc._generate_reset_code()
    expiration = datetime.datetime.now() + datetime.timedelta(hours=6)
    return code, expiration


@function_moved('services.resetcodes.ResetCode._check_reset_code', False)
def check_reset_code(code):
    from services.resetcodes import ResetCode
    rc = ResetCode()
    return rc._check_reset_code


@function_moved('services.emailer.send_email')
def send_email(sender, rcpt, subject, body, smtp_host='localhost',
               smtp_port=25, smtp_user=None, smtp_password=None, **kw):
    pass


@function_moved('services.emailer.valid_email')
def valid_email(email):
    pass
