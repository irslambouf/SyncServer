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
# The Initial Developer of the Original Code is Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
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
User controller. Implements all APIs from:

https://wiki.mozilla.org/Labs/Weave/User/1.0/API

"""
import os
import traceback
import simplejson as json

from webob.exc import (HTTPServiceUnavailable, HTTPBadRequest,
                       HTTPInternalServerError, HTTPNotFound,
                       HTTPUnauthorized)

from routes import URLGenerator

from recaptcha.client import captcha
from cef import log_cef, AUTH_FAILURE, PASSWD_RESET_CLR

from services.util import HTTPJsonBadRequest, valid_password
from services.emailer import send_email, valid_email
from services.exceptions import BackendError
from services.formatters import text_response, json_response
from services.user import extract_username
from services.resetcodes import AlreadySentError
from services.respcodes import (ERROR_MISSING_PASSWORD,
                                ERROR_NO_EMAIL_ADDRESS,
                                ERROR_INVALID_WRITE,
                                ERROR_MALFORMED_JSON,
                                ERROR_WEAK_PASSWORD,
                                ERROR_INVALID_USER,
                                ERROR_INVALID_RESET_CODE,
                                ERROR_INVALID_CAPTCHA,
                                ERROR_USERNAME_EMAIL_MISMATCH)
from services.pluginreg import load_and_configure
from services.user import User, ServicesUser

from syncreg.util import render_mako

#  Node-assignment backends can raise AlreadyWrittenError, and we need to
#  handle it correctly.  But we don't want to introduce a hard dependency
#  on the mozsvcnodes module.  If it can't be imported, create a stub
#  exception that will never be used.
try:
    from mozsvcnodes import AlreadyWrittenError as NodeAlreadyWrittenError
except ImportError:
    class NodeAlreadyWrittenError(Exception):  # NOQA
        def __init__(self, node="null"):
            self.node = node


_TPL_DIR = os.path.join(os.path.dirname(__file__), 'templates')


class UserController(object):

    def __init__(self, app):
        self.app = app
        self.logger = self.app.logger
        self.strict_usernames = app.config.get('auth.strict_usernames', True)
        self.shared_secret = app.config.get('global.shared_secret')
        self.auth = self.app.auth.backend

        # Fail noisily if not used with a new-style auth backend.
        try:
            is_newstyle_auth = isinstance(self.auth, ServicesUser)
        except Exception:
            is_newstyle_auth = False
        if not is_newstyle_auth:
            msg = "This code will only work with new-style auth backends."\
                  " Please set 'auth.backend' to a class from the"\
                  " services.user package."
            raise ValueError(msg)

        try:
            self.reset = load_and_configure(app.config, 'reset_codes')
        except Exception:
            # Have they not configured one, or did it fail to load?
            if 'reset_codes.backend' not in app.config:
                self.logger.debug("No reset code library in place")
            else:
                self.logger.debug(traceback.format_exc())
                self.logger.debug("Reset code library failed to load")
            self.reset = None

        # For large-scale deployments you may want to use a dedicated
        # node-assigment server.  See here for the details:
        #   http://hg.mozilla.org/services/server-node-assignment
        try:
            self.nodes = load_and_configure(app.config, 'nodes')
        except Exception:
            # Have they not configured one, or did it fail to load?
            if 'nodes.backend' not in app.config:
                self.logger.debug("No node assignment library in place")
            else:
                self.logger.debug(traceback.format_exc())
                self.logger.debug("Node assignment library failed to load")
            self.nodes = None

        # For simple deployments, a single fixed node will suffice.
        self.fallback_node = \
                    self.clean_location(app.config.get('nodes.fallback_node'))

    def user_exists(self, request):
        if request.user.get('username') is None:
            raise HTTPNotFound()
        uid = self.auth.get_user_id(request.user)
        return text_response(int(uid is not None))

    def return_fallback(self):
        if self.fallback_node is None:
            msg = "No fallback node has been configured. "\
                  "Please set nodes.fallback_node in your config file."
            raise BackendError(msg)
        return text_response(self.fallback_node)

    def clean_location(self, location):
        if location is None:
            return None
        if not location.endswith('/'):
            location += '/'
        if not location.startswith('http'):
            location = 'https://%s' % location
        return location

    def user_node(self, request):
        """Returns the storage node root for the user"""
        # warning:
        # the client expects a string body not a json body
        # except when the node is 'null'

        # If we're not using a node assignment backend then return fallback.
        if self.nodes is None:
            return self.return_fallback()

        # Look up the user and see if they already have a node assigned.
        self.auth.get_user_info(request.user, ['syncNode'])

        if not request.user.get('userid'):
            return HTTPNotFound()

        if request.user.get('syncNode'):
            syncnode = 'https://%s/' % request.user.get('syncNode')
            return text_response(syncnode)

        # Assign a new node using the backend.
        # This assumes it will remember the assignment, and optimally that
        # it will cache it in the user's syncNode property for our reference.
        try:
            new_node = self.nodes.get_best_node('sync', user=request.user)
        except NodeAlreadyWrittenError, e:
            new_node = e.node
        except Exception:
            self.logger.error(traceback.format_exc())
            self.logger.error("Node assignment failed")
            return json_response(None)

        if new_node is None:
            return json_response(None)

        if new_node != "null":
            if not new_node.startswith('http'):
                new_node = 'https://' + new_node
            if not new_node.endswith('/'):
                new_node = new_node + '/'

        return text_response(new_node)

    def password_reset(self, request, **data):
        """Sends an e-mail for a password reset request."""
        if self.reset is None:
            self.logger.debug('reset attempted, but no resetcode library '
                              'installed')
            raise HTTPServiceUnavailable()

        request.response.headers.add('X-Frame-Options', 'DENY')
        user_id = self.auth.get_user_id(request.user)
        if user_id is None:
            # user not found
            raise HTTPJsonBadRequest(ERROR_INVALID_USER)

        self.auth.get_user_info(request.user, ['mail'])
        if request.user.get('mail') is None:
            raise HTTPJsonBadRequest(ERROR_NO_EMAIL_ADDRESS)

        self._check_captcha(request, data)

        try:
            # the request looks fine, let's generate the reset code
            code = self.reset.generate_reset_code(request.user)

            urlgen = URLGenerator(self.app.mapper, request.environ)
            data = {'user_name': request.user['username'],
                    'code': code,
                    'host': request.host_url,
                    'url': urlgen(controller="user",
                                  action="password_reset_form")}
            body = render_mako('password_reset_mail.mako', **data)

            sender = request.config['smtp.sender']
            host = request.config['smtp.host']
            port = int(request.config['smtp.port'])
            user = request.config.get('smtp.user')
            password = request.config.get('smtp.password')

            subject = 'Resetting your Services password'
            res, msg = send_email(sender, request.user['mail'], subject, body,
                                  host, port, user, password)

            if not res:
                raise HTTPServiceUnavailable(msg)
        except AlreadySentError:
            #backend handled the reset code email. Keep going
            pass

        return text_response('success')

    def delete_password_reset(self, request, **data):
        """Forces a password reset clear"""
        if self.reset is None:
            self.logger.debug('reset attempted, but no resetcode library '
                              'installed')
            raise HTTPServiceUnavailable()

        self._check_captcha(request, data)
        self.auth.get_user_id(request.user)
        self.reset.clear_reset_code(request.user)
        log_cef("User requested password reset clear", 9, request.environ,
                self.app.config, request.user.get('username'),
                PASSWD_RESET_CLR)
        return text_response('success')

    def _check_captcha(self, request, data):
        # check if captcha info are provided
        if not self.app.config['captcha.use']:
            return

        challenge = data.get('captcha-challenge')
        response = data.get('captcha-response')

        if challenge is not None and response is not None:
            resp = captcha.submit(challenge, response,
                                  self.app.config['captcha.private_key'],
                                  remoteip=request.remote_addr)
            if not resp.is_valid:
                raise HTTPJsonBadRequest(ERROR_INVALID_CAPTCHA)
        else:
            raise HTTPJsonBadRequest(ERROR_INVALID_CAPTCHA)

    def create_user(self, request):
        """Creates a user."""
        if self.auth.get_user_id(request.user):
            raise HTTPJsonBadRequest(ERROR_INVALID_WRITE)
        username = request.user['username']

        try:
            data = json.loads(request.body)
        except ValueError:
            raise HTTPJsonBadRequest(ERROR_MALFORMED_JSON)

        email = data.get('email')
        if email and not valid_email(email):
            raise HTTPJsonBadRequest(ERROR_NO_EMAIL_ADDRESS)

        # checking that the e-mail matches the username
        munged_email = extract_username(email)
        if munged_email != username and self.strict_usernames:
            raise HTTPJsonBadRequest(ERROR_USERNAME_EMAIL_MISMATCH)

        password = data.get('password')
        if not password:
            raise HTTPJsonBadRequest(ERROR_MISSING_PASSWORD)

        if not valid_password(username, password):
            raise HTTPJsonBadRequest(ERROR_WEAK_PASSWORD)

        # check if captcha info are provided or if we bypass it
        if (self.shared_secret is None or
            request.headers.get('X-Weave-Secret') != self.shared_secret):
            self._check_captcha(request, data)

        # all looks good, let's create the user
        if not self.auth.create_user(request.user['username'], password,
                                     email):
            raise HTTPInternalServerError('User creation failed.')

        return request.user['username']

    def change_email(self, request):
        """Changes the user e-mail"""

        # the body is in plain text
        email = request.body

        if not valid_email(email):
            raise HTTPJsonBadRequest(ERROR_NO_EMAIL_ADDRESS)

        if not hasattr(request, 'user_password'):
            raise HTTPBadRequest()

        if not self.auth.update_field(request.user, request.user_password,
                                      'mail', email):
            raise HTTPInternalServerError('User update failed.')

        return text_response(email)

    def change_password(self, request):
        """Changes the user's password

        Takes a classical authentication or a reset code
        """
        # the body is in plain text utf8 string
        new_password = request.body.decode('utf8')

        if not valid_password(request.user.get('username'), new_password):
            raise HTTPBadRequest('Password should be at least 8 '
                                 'characters and not the same as your '
                                 'username')

        key = request.headers.get('X-Weave-Password-Reset')

        if key is not None:
            user_id = self.auth.get_user_id(request.user)

            if user_id is None:
                raise HTTPNotFound()

            if not self.reset.verify_reset_code(request.user, key):
                log_cef('Invalid Reset Code submitted', 5, request.environ,
                        self.app.config, request.user['username'],
                        'InvalidResetCode', submitedtoken=key)

                raise HTTPJsonBadRequest(ERROR_INVALID_RESET_CODE)

            if not self.auth.admin_update_password(request.user,
                                                   new_password, key):
                raise HTTPInternalServerError('Password change failed '
                                              'unexpectedly.')
        else:
            # classical auth
            self.app.auth.authenticate_user(request, self.app.config,
                                            request.user['username'])

            if request.user['userid'] is None:
                log_cef('User Authentication Failed', 5, request.environ,
                        self.app.config, request.user['username'],
                        AUTH_FAILURE)
                raise HTTPUnauthorized()

            if not self.auth.update_password(request.user,
                                             request.user_password,
                                             new_password):
                raise HTTPInternalServerError('Password change failed '
                                              'unexpectedly.')

        return text_response('success')

    def password_reset_form(self, request, **kw):
        """Returns a form for resetting the password"""
        request.response.headers.add('X-Frame-Options', 'DENY')
        urlgen = URLGenerator(self.app.mapper, request.environ)
        kw["url"] = urlgen(controller="user", action="password_reset_form")
        if 'key' in kw or 'error' in kw:
            # we have a key, let's display the key controlling form
            return render_mako('password_reset_form.mako', **kw)
        elif not request.POST and not request.GET:
            # asking for the first time
            return render_mako('password_ask_reset_form.mako', **kw)

        raise HTTPBadRequest()

    def _repost(self, request, error):
        request.POST['error'] = error
        return self.password_reset_form(request, **dict(request.POST))

    def do_password_reset(self, request):
        """Do a password reset."""
        if self.reset is None:
            self.logger.debug('reset attempted, but no resetcode library '
                              'installed')
            raise HTTPServiceUnavailable()

        request.response.headers.add('X-Frame-Options', 'DENY')
        user_name = request.POST.get('username')
        if user_name is not None:
            user_name = extract_username(user_name)

        if request.POST.keys() == ['username']:
            # setting up a password reset
            # XXX add support for captcha here via **data
            request.user = User(user_name)
            try:
                self.password_reset(request)
            except (HTTPServiceUnavailable, HTTPJsonBadRequest), e:
                return render_mako('password_failure.mako', error=e.detail)
            else:
                return render_mako('password_key_sent.mako')

            raise HTTPJsonBadRequest()

        # full form, the actual password reset
        password = request.POST.get('password')
        confirm = request.POST.get('confirm')
        key = request.POST.get('key')

        if key is None:
            raise HTTPJsonBadRequest()

        if user_name is None:
            return self._repost(request,
                                'Username not provided. Please check '
                                'the link you used.')

        user = User(user_name)
        user_id = self.auth.get_user_id(user)
        if user_id is None:
            return self._repost(request, 'We are unable to locate your '
                                'account')

        if password is None:
            return self._repost(request, 'Password not provided. '
                                'Please check the link you used.')

        if password != confirm:
            return self._repost(request, 'Password and confirmation do '
                                'not match')

        if not valid_password(user_name, password):
            return self._repost(request, 'Password should be at least 8 '
                                'characters and not the same as your '
                                'username')

        if not self.reset.verify_reset_code(user, key):
            return self._repost(request, 'Key does not match with username. '
                                'Please request a new key.')

        # everything looks fine
        if not self.auth.admin_update_password(user, password):
            return self._repost(request, 'Password change failed '
                                         'unexpectedly.')

        self.reset.clear_reset_code(user)
        return render_mako('password_changed.mako')

    def delete_user(self, request):
        """Deletes the user."""

        if not hasattr(request, 'user_password'):
            raise HTTPBadRequest()

        res = self.auth.delete_user(request.user, request.user_password)
        return text_response(int(res))

    def _captcha(self):
        """Return HTML string for inserting recaptcha into a form."""
        return captcha.displayhtml(self.app.config['captcha.public_key'],
                                   use_ssl=self.app.config['captcha.use_ssl'])

    def captcha_form(self, request):
        """Renders the captcha form"""
        if not self.app.config['captcha.use']:
            raise HTTPNotFound('No captcha configured')

        return render_mako('captcha.mako', captcha=self._captcha())
