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
#   Toby Elliott (telliott@mozilla.com)
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
""" Reset code manager.

Stores the reset codes in memcache/membase, per user name/product.

"""
from memcache import Client

from services.resetcodes import ResetCode
from services.util import BackendError

_6HOURS = 21600


class ResetCodeMemcache(ResetCode):
    """ Implements the reset code methods for auth backends.
    """
    def __init__(self, product='auth', nodes=None, debug=0,
                 expiration=_6HOURS, **kw):
        if nodes is None:
            nodes = ['127.0.0.1:11211']

        self._engine = Client(nodes, debug)
        self.product = product
        self.expiration = expiration

    #
    # Private methods
    #
    def _get_reset_code(self, user_id):
        return self._engine.get(self._generate_key(user_id))

    def _generate_key(self, user_id):
        return "reset:%s:%s" % (user_id, self.product)

    def _set_reset_code(self, user_id):
        code = self._generate_reset_code()
        key = self._generate_key(user_id)
        if not self._engine.set(key, code, self.expiration):
            raise BackendError()

        return code

    #
    # Public methods
    #
    def generate_reset_code(self, user, overwrite=False):
        user_id = self._get_user_id(user)
        if not overwrite:
            stored_code = self._get_reset_code(user_id)
            if stored_code is not None:
                return stored_code

        return self._set_reset_code(user_id)

    def verify_reset_code(self, user, code):
        user_id = self._get_user_id(user)
        if not self._check_reset_code(code):
            return False

        stored_code = self._get_reset_code(user_id)
        if stored_code is None:
            return False

        return stored_code == code

    def clear_reset_code(self, user):
        user_id = self._get_user_id(user)
        return self._engine.delete(self._generate_key(user_id))
