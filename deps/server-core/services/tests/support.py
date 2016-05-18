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
# Portions created by the Initial Developer are Copyright (C) 2011
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
import os
import smtplib
import contextlib
import uuid
from email import message_from_string
from ConfigParser import RawConfigParser

from webob import Request

from metlog.holder import CLIENT_HOLDER
from metlog.senders.dev import DebugCaptureSender
from metlog.client import MetlogClient

import metlog_cef.cef_plugin

from services.config import Config
from services.pluginreg import load_and_configure


if "MOZSVC_UUID" not in os.environ:
    os.environ["MOZSVC_UUID"] = str(uuid.uuid4())


class TestEnv(object):
    """Class representing the configuration environment for the tests.
    """
    def __init__(self, ini_path=None, ini_dir=None, load_sections=None):
        """
        :param ini_dir: Directory path in which to start looking for the ini
        file.  Will climb the file tree from here looking for 'tests.ini' file,
        unless 'WEAVE_TESTFILE' env var is set, in which case it will climb the
        file tree from here looking for 'tests_${WEAVE_TESTFILE}.ini'.

        :param ini_path: Full path to configuration file.  Takes precedence
        over ini_dir, if both are provided.  Raises IOError if file doesn't
        exist.

        One or the other of `ini_dir` or `ini_path` arguments MUST be provided.

        :param load_sections: A sequence of strings that name the configuration
        sections that should be dynamically loaded.  Any entry in this sequence
        could alternately be a 2-tuple containing the name of the section and
        the corresponding class parameter value to use.
        """
        self.start_dir = ini_dir
        if ini_path:
            if not os.path.isfile(ini_path):
                raise IOError("invalid config file: %s" % ini_path)
            ini_dir = os.path.dirname(ini_path)
        elif ini_dir:
            if 'WEAVE_TESTFILE' in os.environ:
                test_filename = 'tests_%s.ini' % os.environ['WEAVE_TESTFILE']
            else:
                test_filename = 'tests.ini'

            while True:
                ini_path = os.path.join(ini_dir, test_filename)
                if os.path.exists(ini_path):
                    break

                if ini_path == ("/%s" % test_filename) \
                    or ini_path == test_filename:
                    raise IOError("cannot locate %s" % test_filename)

                ini_dir = os.path.split(ini_dir)[0]
            else:
                raise ValueError('No ini_path or ini_dir specified.')

        self.ini_dir = ini_dir
        self.ini_path = ini_path

        ini_cfg = RawConfigParser()
        ini_cfg.read(ini_path)

        # loading loggers
        self.config = self.convert_config(ini_cfg, ini_path)

        # Ensure that metlog is available, either from the config
        # or by setting up a default client.
        try:
            loader = load_and_configure(self.config, "metlog_loader")
            client = loader.default_client
        except KeyError:
            sender = DebugCaptureSender()
            client = MetlogClient(sender, "syncserver")
        CLIENT_HOLDER.set_client(client.logger, client)
        if not hasattr(client, "cef"):
            log_cef_fn = metlog_cef.cef_plugin.config_plugin(dict())
            client.add_method(log_cef_fn)

        if load_sections is not None:
            for section in load_sections:
                if isinstance(section, tuple):
                    self.add_class(section[0], cls_param=section[1])
                else:
                    self.add_class(section)

    def convert_config(self, ini_cfg, ini_path):
        here = {'here': os.path.dirname(os.path.realpath(ini_path))}
        cfg_in = dict([(key, value % here) for key, value in
                       ini_cfg.items('DEFAULT') + ini_cfg.items('app:main')])
        return Config(cfg_in)

    def add_class(self, section, cls_param="backend"):
        """Takes the name of a config section and uses it to instantiate a
        class and put it into the env at self.[name]"""
        setattr(self, section,
                load_and_configure(self.config, section, cls_param))


def patch_captcha(valid=True):
    """patches captcha for testing to automatically return true or false"""
    from recaptcha.client import captcha

    class Result(object):
        is_valid = valid

    def submit(*args, **kw):
        return Result()

    captcha.submit = submit

    def displayhtml(key, use_ssl=False):
        return """<form>
             key is %s
          </form>""" % key

    captcha.displayhtml = displayhtml


# non-class way of doing this
def initenv(config=None, **env_args):
    """Reads the config file and instantiates an auth."""
    env_args.setdefault('load_sections', ['auth'])
    if not config:
        env_args.setdefault('ini_dir', os.path.dirname(__file__))
    else:
        env_args['ini_path'] = config
    testenv = TestEnv(**env_args)
    return testenv.ini_dir, testenv.config, testenv.auth


def cleanupenv(config=None, **env_args):
    """Reads the config file and cleans up any sqlite database files."""
    env_args.setdefault('load_sections', [])
    if not config:
        env_args.setdefault('ini_dir', os.path.dirname(__file__))
    else:
        env_args['ini_path'] = config
    testenv = TestEnv(**env_args)
    for key in testenv.config:
        if key.rsplit(".", 1)[-1] == "sqluri":
            sqluri = testenv.config[key]
            sqlfile = sqluri.split('sqlite:///')[-1]
            if sqlfile != sqluri and os.path.exists(sqlfile):
                os.remove(sqlfile)


def check_memcache():
    try:
        import memcache   # NOQA
    except ImportError:
        return False

    #see if we have a memcache install
    engine = memcache.Client(['127.0.0.1:11211'])
    if not engine.set('test:foo', 1):
        return False
    engine.delete('test:foo')
    return True


def get_app(wrapped):
    app = wrapped
    while True:
        if hasattr(app, 'app'):
            app = app.app
        elif hasattr(app, 'application'):
            app = app.application
        else:
            return app


def create_test_app(application):
    """Returns a TestApp instance.

    If TEST_REMOTE is set in the environ, will run against a real server.
    """
    import urlparse
    from wsgiproxy.exactproxy import proxy_exact_request
    from webtest import TestApp

    # runs over a proxy
    if os.environ.get('TEST_REMOTE'):
        parsed = urlparse.urlsplit(os.environ['TEST_REMOTE'])
        if ':' in parsed.netloc:
            loc, port = parsed.netloc.split(':')
        else:
            loc = parsed.netloc
            if parsed.scheme == 'https':
                port = '443'
            else:
                port = '80'

        extra = {'HTTP_HOST': parsed.netloc,
                 'SERVER_NAME': loc,
                 'SERVER_PORT': port,
                 'wsgi.url_scheme': parsed.scheme}

        return TestApp(proxy_exact_request, extra_environ=extra)

    # regular instance
    return TestApp(application)


class _FakeSMTP(object):

    msgs = []

    def __init__(self, *args, **kw):
        pass

    def quit(self):
        pass

    def sendmail(self, sender, rcpts, msg):
        self.msgs.append((sender, rcpts, msg))


def patch_smtp():
    smtplib.old = smtplib.SMTP
    smtplib.SMTP = _FakeSMTP


def unpatch_smtp():
    smtplib.SMTP = smtplib.old


def get_sent_email(index=-1):
    sender, rcpts, msg = _FakeSMTP.msgs[index]
    msg = message_from_string(msg)
    return sender, rcpts, msg


try:
    import wsgi_intercept  # NOQA
    CAN_MOCK_WSGI = True
except ImportError:
    CAN_MOCK_WSGI = False


@contextlib.contextmanager
def mock_wsgi(callable=None, server='localhost', port=80):
    from wsgi_intercept import add_wsgi_intercept as add
    from wsgi_intercept import remove_wsgi_intercept as remove
    from wsgi_intercept.http_client_intercept import install, uninstall

    install()
    add(server, port, callable)
    try:
        yield
    finally:
        remove(server, port)
        uninstall()


def make_request(path, environ=None, **kwds):
    """Helper function to make stub Request objects.

    This function creates a new Request object from the given path and
    environment data, then sets any additional keyword arguments on the
    object before returning it.  If you omit the environment then a
    sensible default is calculated from the path.

    Use it as a shortcut to build requests for testing, by specifying only
    the information you care about.  Like so::

        req = make_request("/", method="POST", host="here")

    """
    request = Request.blank(path, environ)
    for (attr, value) in kwds.iteritems():
        setattr(request, attr, value)
    return request
