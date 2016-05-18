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
#   Rob Miller (rmiller@mozilla.com)
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
Application entry point.
"""
import traceback
import simplejson as json
import sys
import signal
from time import sleep

from metlog.client import MetlogClient
from metlog.decorators.stats import incr_count
from metlog.holder import CLIENT_HOLDER
from metlog.senders.logging import StdLibLoggingSender

import metlog_cef.cef_plugin

from paste.translogger import TransLogger
from paste.exceptions.errormiddleware import ErrorMiddleware

from routes import Mapper

from webob import Response
from webob.dec import wsgify
from webob.exc import (HTTPNotFound, HTTPServiceUnavailable,
                       HTTPException, HTTPMethodNotAllowed)

from services.util import (CatchErrorMiddleware, round_time, BackendError,
                           create_hash, HTTPJsonServiceUnavailable)
from services.config import Config
from services.controllers import StandardController
from services.events import REQUEST_STARTS, REQUEST_ENDS, APP_ENDS, notify
from services.metrics import send_services_data, svc_timeit
from services.pluginreg import load_and_configure
from services.user import User


class SyncServerApp(object):
    """ Dispatches the request to the right controller by using Routes.
    """
    def __init__(self, urls, controllers, config=None,
                 auth_class=None):
        self.mapper = Mapper()
        if config is None:
            self.config = Config()
        elif isinstance(config, Config):
            self.config = config
        else:
            # try to convert to config object
            self.config = Config(config)

        # global config
        self.retry_after = self.config.get('global.retry_after', 1800)

        # heartbeat page
        self.heartbeat_page = self.config.get('global.heartbeat_page',
                                              '__heartbeat__')

        # debug page, if any
        self.debug_page = self.config.get('global.debug_page')

        # check if we want to clean when the app ends
        self.sigclean = self.config.get('global.clean_shutdown', True)

        # load the specified plugin modules
        self.modules = dict()
        app_modules = self.config.get('app.modules', [])
        if isinstance(app_modules, basestring):
            app_modules = [app_modules]
        for module in app_modules:
            self.modules[module] = load_and_configure(self.config, module)

        if self.modules.get('metlog_loader') is not None:
            # stash the metlog client in a more convenient spot
            self.logger = self.modules.get('metlog_loader').default_client
        else:
            # there was no metlog config, default to using StdLibLoggingSender
            sender = StdLibLoggingSender('syncserver', json_types=[])
            metlog = MetlogClient(sender, 'syncserver')
            CLIENT_HOLDER.set_client(metlog.logger, metlog)
            self.logger = metlog
        if not hasattr(self.logger, "cef"):
            log_cef_fn = metlog_cef.cef_plugin.config_plugin(dict())
            self.logger.add_method(log_cef_fn)

        # XXX: this should be converted to auto-load in self.modules
        # loading the authentication tool
        self.auth = None if auth_class is None else auth_class(self.config)

        # loading and connecting controllers
        self.controllers = dict([(name, klass(self)) for name, klass in
                                 controllers.items()])

        for url in urls:
            if len(url) == 4:
                verbs, match, controller, action = url
                extras = {}
            elif len(url) == 5:
                verbs, match, controller, action, extras = url
            else:
                msg = "Each URL description needs 4 or 5 elements. Got %s" \
                    % str(url)
                raise ValueError(msg)

            if isinstance(verbs, str):
                verbs = [verbs]

            # wrap action methods w/ metlog decorators
            controller_instance = self.controllers.get(controller)
            if controller_instance is not None:
                wrapped_name = '_%s_wrapped' % action
                method = getattr(controller_instance, action, None)
                if ((method is not None) and
                    (not hasattr(controller_instance, wrapped_name))):
                    # add wrapped method
                    wrapped = svc_timeit(method)
                    wrapped = incr_count(wrapped)
                    wrapped = send_services_data(wrapped)
                    setattr(controller_instance, wrapped_name, wrapped)
            self.mapper.connect(None, match, controller=controller,
                                action=action, conditions=dict(method=verbs),
                                **extras)

        # loads host-specific configuration
        self._host_configs = {}

        # heartbeat & debug pages
        self.standard_controller = StandardController(self)

        # rehooked overridable points so they can be overridden in the base app
        self.standard_controller._debug_server = self._debug_server
        self.standard_controller._check_server = self._check_server

        # hooking callbacks when the app shuts down
        self.killing = self.shutting = False
        self.graceful_shutdown_interval = self.config.get(
                                      'global.graceful_shutdown_interval', 1.)
        self.hard_shutdown_interval = self.config.get(
                                          'global.hard_shutdown_interval', 1.)
        if self.sigclean:
            signal.signal(signal.SIGTERM, self._sigterm)
            signal.signal(signal.SIGINT, self._sigterm)

    def _sigterm(self, signal, frame):
        self.shutting = True

        # wait for a bit
        sleep(self.graceful_shutdown_interval)

        # no more queries
        self.killing = True

        # wait for a bit
        sleep(self.hard_shutdown_interval)

        # now we can notify the end -- so pending stuff can be cleaned up
        notify(APP_ENDS)

        # bye-bye
        sys.exit(0)

    def _before_call(self, request):
        return {}

    def _host_specific(self, host, config):
        """Will compute host-specific requests"""
        return config.merge('host:%s' % host)

    #
    # Debug & heartbeat pages
    #
    def _debug_server(self, request):
        return []

    def _check_server(self, request):
        pass

    def _debug(self, request):
        return self.standard_controller._debug(request)

    def _heartbeat(self, request):
        return self.standard_controller._heartbeat(request)

    # events fired when a request is handled
    def _notified(func):
        def __notified(self, request):
            notify(REQUEST_STARTS, request)
            response = None
            try:
                response = func(self, request)
                return response
            finally:
                notify(REQUEST_ENDS, response)
        return __notified

    # information dumped in error logs
    def get_infos(self, request):
        """Returns a mapping containing useful info.

        It can be related to the request, or global to the app.
        """
        return {'user': str(request.user)}

    #
    # entry point
    #
    @wsgify
    @_notified
    def __call__(self, request):
        """Entry point for the WSGI app."""
        # the app is being killed, no more requests please
        if self.killing:
            raise HTTPServiceUnavailable()

        request.server_time = round_time()

        # gets request-specific config
        request.config = self._host_specific(request.host, self.config)

        # pre-hook
        before_headers = self._before_call(request)

        try:
            response = self._dispatch_request(request)
        except HTTPException, response:
            # set before-call headers on all responses
            response.headers.update(before_headers)
            raise
        else:
            # set X-Weave-Timestamp on success responses
            response.headers['X-Weave-Timestamp'] = str(request.server_time)
            response.headers.update(before_headers)
            return response

    def _dispatch_request(self, request):
        """Dispatch the request.

        This will dispatch the request either to a special internal handler
        or to one of the configured controller methods.
        """
        # XXX
        # removing the trailing slash - ambiguity on client side
        url = request.path_info.rstrip('/')
        if url != '':
            request.environ['PATH_INFO'] = request.path_info = url

        # the heartbeat page is called
        if url == '/%s' % self.heartbeat_page:
            # the app is shutting down, we want to return a 503
            if self.shutting:
                raise HTTPServiceUnavailable()

            # otherwise we do call the heartbeat page
            if (self.heartbeat_page is not None and
                request.method in ('HEAD', 'GET')):
                return self._heartbeat(request)

        # the debug page is called
        if self.debug_page is not None and url == '/%s' % self.debug_page:
            return self._debug(request)

        # the request must be going to a controller method
        match = self.mapper.routematch(environ=request.environ)

        if match is None:
            # Check whether there is a match on just the path.
            # If not then it's a 404; if so then it's a 405.
            if request.path_info:
                match = self.mapper.routematch(url=request.path_info)
            if match is None:
                return HTTPNotFound()
            else:
                return HTTPMethodNotAllowed()

        match, __ = match

        # if auth is enabled, wrap it around the call to the controller
        if self.auth is None:
            return self._dispatch_request_with_match(request, match)
        else:
            self.auth.check(request, match)
            try:
                response = self._dispatch_request_with_match(request, match)
            except HTTPException, response:
                self.auth.acknowledge(request, response)
                raise
            else:
                self.auth.acknowledge(request, response)
                return response

    def _dispatch_request_with_match(self, request, match):
        """Dispatch a request according to a URL routing match."""
        function = self._get_function(match['controller'], match['action'])
        if function is None:
            raise HTTPNotFound('Unknown URL %r' % request.path_info)

        # extracting all the info from the headers and the url
        request.sync_info = match

        # creating a user object to be passed around the request, if one hasn't
        # already been set
        if not hasattr(request, 'user'):
            request.user = User()
            if 'username' in request.sync_info:
                request.user['username'] = request.sync_info['username']
            if 'user_id' in request.sync_info:
                request.user['userid'] = request.sync_info['user_id']

        params = self._get_params(request)
        try:
            result = function(request, **params)
        except BackendError as err:
            err.request = request
            err_info = str(err)
            err_trace = traceback.format_exc()
            extra_info = ['%s: %s' % (key, value)
                          for key, value in self.get_infos(request).items()]
            extra_info = '\n'.join(extra_info)
            error_log = '%s\n%s\n%s' % (err_info, err_trace, extra_info)
            hash = create_hash(error_log)
            self.logger.error(hash)
            self.logger.error(error_log)
            msg = json.dumps("application error: crash id %s" % hash)
            if err.retry_after is not None:
                if err.retry_after == 0:
                    retry_after = None
                else:
                    retry_after = err.retry_after
            else:
                retry_after = self.retry_after

            raise HTTPJsonServiceUnavailable(msg, retry_after=retry_after)

        # create the response object in case we get back a string
        response = self._create_response(request, result, function)
        return response

    def _get_params(self, request):
        # the GET mapping is filled on GET and DELETE requests
        if request.method in ('GET', 'DELETE'):
            return dict(request.GET)
        return {}

    def _create_response(self, request, result, function):
        if not isinstance(result, basestring):
            # result is already a Response
            return result

        response = getattr(request, 'response', None)
        if response is None:
            response = Response(result)
        elif isinstance(result, str):
            response.body = result
        else:
            # if it's not str it's unicode, which really shouldn't happen
            module = getattr(function, '__module__', 'unknown')
            name = getattr(function, '__name__', 'unknown')
            self.logger.warn('Unicode response returned from: %s - %s'
                        % (module, name))
            response.unicode_body = result
        return response

    def _get_function(self, controller, action):
        """Return the action of the right controller."""
        try:
            controller = self.controllers[controller]
        except KeyError:
            return None
        wrapped_name = '_%s_wrapped' % action
        fn = getattr(controller, wrapped_name, None)
        if fn is None:
            fn = getattr(controller, action, None)
        return fn


def set_app(urls, controllers, klass=SyncServerApp, auth_class=None,
            wrapper=None):
    """make_app factory."""
    def make_app(global_conf, **app_conf):
        """Returns a Sync Server Application."""
        global_conf.update(app_conf)
        params = Config(global_conf)
        app = klass(urls, controllers, params, auth_class)

        if params.get('debug', False):
            app = TransLogger(app, logger_name='syncserver',
                              setup_console_handler=True)

        if params.get('profile', False):
            from repoze.profile.profiler import AccumulatingProfileMiddleware
            app = AccumulatingProfileMiddleware(app,
                                          log_filename='profile.log',
                                          cachegrind_filename='cachegrind.out',
                                          discard_first_request=True,
                                          flush_at_shutdown=True,
                                          path='/__profile__')

        if params.get('client_debug', False):
            # errors are displayed in the user client
            app = ErrorMiddleware(app, debug=True,
                                  show_exceptions_in_wsgi_errors=True)
        else:
            # errors are logged and a 500 is returned with an empty body
            # to avoid any security whole
            app = CatchErrorMiddleware(app, logger_name='syncserver')

        if wrapper is not None:
            app = wrapper(app, config=params)
        return app
    return make_app
