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
# Portions created by the Initial Developer are Copyright (C) 2012
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Ryan Kelly (rfkelly@mozilla.com)
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
Custom gevent-based worker class for gunicorn.

This module provides a custom GeventWorker subclass for gunicorn, with some
extra operational niceties.
"""

import os
import sys
import time
import thread
import signal
import traceback

import greenlet
import gevent.hub

from gunicorn.workers.ggevent import GeventWorker

from metlog.holder import CLIENT_HOLDER

# Take references to un-monkey-patched versions of stuff we need.
# Monkey-patching will have already been done by the time we come to
# use these functions at runtime.
_real_sleep = time.sleep
_real_start_new_thread = thread.start_new_thread
_real_get_ident = thread.get_ident


# The maximum amount of time that the eventloop can be blocked
# without causing an error to be logged.
MAX_BLOCKING_TIME = float(os.environ.get("GEVENT_MAX_BLOCKING_TIME", 0.1))


# The filename for dumping memory usage data.
MEMORY_DUMP_FILE = os.environ.get("MOZSVC_MEMORY_DUMP_FILE",
                                  "/tmp/mozsvc-memdump")


class MozSvcWorker(GeventWorker):
    """Custom gunicorn worker with extra operational niceties.

    This is a custom gunicorn worker class, based on the standard gevent worker
    but with some extra operational- and debugging-related features:

        * a background thread that monitors for blocking of the gevent
          event-loop, and logs tracebacks if blocking code is found.

        * a timeout enforced on each individual request, rather than on
          inactivity of the worker as a whole.

        * a signal handler to dump memory usage data on SIGUSR2.

    To detect eventloop blocking, the worker installs a greenlet trace
    function that increments a counter on each context switch.  A background
    (os-level) thread monitors this counter and prints a traceback if it has
    not changed within a configurable number of seconds.
    """

    def init_process(self):
        # Set up a greenlet tracing hook to monitor for event-loop blockage,
        # but only if monitoring is both possible and required.
        if hasattr(greenlet, "settrace") and MAX_BLOCKING_TIME > 0:
            # Grab a reference to the gevent hub.
            # It is needed in a background thread, but it only visible from
            # the main thread, so we need to store a reference to it.
            self._active_hub = gevent.hub.get_hub()
            # Set up a trace function to record each greenlet switch.
            self._active_greenlet = None
            self._greenlet_switch_counter = 0
            greenlet.settrace(self._greenlet_switch_tracer)
            # Create a real thread to monitor for blocking of greenlets.
            # Since this will be a long-running daemon thread, it's OK to
            # fire-and-forget using the low-level start_new_thread function.
            self._main_thread_id = _real_get_ident()
            _real_start_new_thread(self._greenlet_blocking_monitor, ())

        # Continue to superclass initialization logic.
        # Note that this runs the main loop and never returns.
        super(MozSvcWorker, self).init_process()

    def init_signals(self):
        # Leave all signals defined by the superclass in place.
        super(MozSvcWorker, self).init_signals()

        # Hook up SIGUSR2 to dump memory usage information.
        # This will be useful for debugging memory leaks and the like.
        signal.signal(signal.SIGUSR2, self._dump_memory_usage)
        if hasattr(signal, "siginterrupt"):
            signal.siginterrupt(signal.SIGUSR2, False)

    def handle_request(self, *args):
        # Apply the configured 'timeout' value to each individual request.
        # Note that self.timeout is set to half the configured timeout by
        # the arbiter, so we use the value directly from the config.
        with gevent.Timeout(self.cfg.timeout):
            return super(MozSvcWorker, self).handle_request(*args)

    def _greenlet_switch_tracer(self, what, (origin, target)):
        """Callback method executed on every greenlet switch.

        The worker arranges for this method to be called on every greenlet
        switch.  It keeps track of which greenlet is currently active and
        increments a counter to track how many switches have been performed.
        """
        # Sanity-check that this function is being called on every
        # greenlet switch.  Once we're confident it's working correctly
        # then this can be removed.
        if self._active_greenlet not in (None, origin):
            msg = "MozSvcWorker missed a greenlet switch"
            self._log_error(msg)
        # Increment the counter to indicate that a switch took place.
        # This will periodically be reset to zero by the monitoring thread,
        # so we don't need to worry about it growing without bound.
        self._active_greenlet = target
        self._greenlet_switch_counter += 1

    def _greenlet_blocking_monitor(self):
        """Method run in background thread that checks for regular switches.

        This method is an endless loop that gets executed in a background
        thread.  It periodically wakes up and checks whether the active
        greenlet has switched since it was last checked.  If not then an
        error log is generated.

        The only exception is for the greenlet running the gevent Hub, which
        is allowed to block indefinitely while waiting for I/O.
        """
        try:
            while True:
                # Check the switch counter before and after a sleep.
                # If it hasn't increased then the active greenlet is blocking.
                old_switch_counter = self._greenlet_switch_counter
                _real_sleep(MAX_BLOCKING_TIME)
                active_greenlet = self._active_greenlet
                new_switch_counter = self._greenlet_switch_counter
                # If we have detected a successful switch, reset the counter
                # to zero.  This might race with it being incrememted in the
                # other thread, but should succeed often enough to prevent
                # the counter from growing without bound.
                if new_switch_counter != old_switch_counter:
                    self._greenlet_switch_counter = 0
                # If we detected a blocking greenlet, grab the stack trace
                # and log an error.  The active greenlet's frame is not
                # available from the greenlet object itself, we have to look
                # up the current frame of the main thread for the traceback.
                else:
                    if active_greenlet not in (None, self._active_hub):
                        frame = sys._current_frames()[self._main_thread_id]
                        stack = traceback.format_stack(frame)
                        err_log = ["Greenlet appears to be blocked\n"] + stack
                        self._log_error("".join(err_log))
        except Exception:
            # Swallow any exceptions raised during interpreter shutdown.
            # Daemonic Thread objects have this same behaviour.
            if sys is not None:
                raise

    def _log_error(self, msg):
        """Log an error message.

        This will send the error message out via metlog if it is configured,
        or to stderr otherwise.
        """
        logger = CLIENT_HOLDER.default_client
        if logger is not None:
            logger.error(msg)
        else:
            print>>sys.stderr, msg

    def _dump_memory_usage(self, *args):
        """Dump memory usage data to a file.

        This method writes out memory usage data for the current process into
        a timestamped file.  By default the data is written to a file named
        /tmp/mozsvc-memdump.<pid>.<timestamp> but this can be customized
        with the environment variable "MOSVC_MEMORY_DUMP_FILE".

        If the "meliae" package is not installed or if an error occurs during
        processing, then the file "mozsvc-memdump.error.<pid>.<timestamp>"
        will be written with a traceback of the error.
        """
        now = int(time.time())
        try:
            filename = "%s.%d.%d" % (MEMORY_DUMP_FILE, os.getpid(), now)
            from meliae import scanner
            scanner.dump_all_objects(filename)
        except Exception:
            filename = "%s.error.%d.%d" % (MEMORY_DUMP_FILE, os.getpid(), now)
            with open(filename, "w") as f:
                f.write("ERROR DUMPING MEMORY USAGE\n\n")
                traceback.print_exc(file=f)
