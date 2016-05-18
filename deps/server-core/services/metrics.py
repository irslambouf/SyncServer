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
#   Victor Ng (vng@mozilla.com)
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
server-core plugin to set up metlog.
"""
from contextlib import contextmanager
from metlog.config import client_from_stream_config
from metlog.decorators.base import MetlogDecorator
from metlog.decorators.stats import timeit
from metlog.holder import CLIENT_HOLDER
import threading


_LOCAL_STORAGE = threading.local()


def MetlogLoader(**kwargs):
    # Delegates to metlog-py's client configuration functions
    cfgfilepath = kwargs['config']
    with open(cfgfilepath) as cfgfile:
        metlog = client_from_stream_config(cfgfile, 'metlog')
        CLIENT_HOLDER.set_client(metlog.logger, metlog)
    return CLIENT_HOLDER


def update_metlog_data(update_data):
    """
    Update the 'metlog_data' dictionary for this request w/ the provided data.
    """
    if not hasattr(_LOCAL_STORAGE, 'metlog_data'):
        raise AttributeError("No `metlog_data`; are you in a "
                             "thread_context?")
    _LOCAL_STORAGE.metlog_data.update(update_data)


@contextmanager
def thread_context(callback):
    """
    This is a context manager that accepts a callback function and returns a
    thread local dictionary object. Upon exit, the callback function will be
    called and passed that dictionary as the sole argument, after which the
    dictionary will be deleted.
    """
    _LOCAL_STORAGE.metlog_data = dict()
    yield _LOCAL_STORAGE.metlog_data
    try:
        if _LOCAL_STORAGE.metlog_data:
            callback(_LOCAL_STORAGE.metlog_data)
    finally:
        del _LOCAL_STORAGE.metlog_data


class send_services_data(MetlogDecorator):
    """
    Decorator that wraps a function with a threadlocal metlog data dictionary.
    Anything written into this dictionary from within the decorated code will
    be sent as a 'services' message through metlog when the function returns.
    """
    def metlog_call(self, *args, **kwargs):
        req = args[0]

        def send_logmsg(metlog_data):
            self.client.metlog('services', fields=metlog_data)

        with thread_context(send_logmsg) as metlog_data:
            metlog_data['userid'] = req.user['userid']
            return self._fn(*args, **kwargs)


class svc_timeit(timeit):
    """
    Record timer value in services data.
    """
    def metlog_call(self, *args, **kwargs):
        if self.args is None:
            self.args = tuple()
        if self.kwargs is None:
            self.kwargs = {'name': self._fn_fq_name}
        with self.client.timer(*self.args, **self.kwargs) as timer:
            result = self._fn(*args, **kwargs)
        update_metlog_data({'req_time': timer.result})
        return result
