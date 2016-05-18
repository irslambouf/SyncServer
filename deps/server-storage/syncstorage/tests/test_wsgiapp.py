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
#   Ryan Kelly (rkelly@mozilla.com)
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
import unittest
import os
import base64
import json
import random
import collections

from webtest import TestApp

from syncstorage import wsgiapp

# This establishes the MOZSVC_UUID environment variable.
import syncstorage.tests.support  # NOQA

BASE_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "sync.conf")


class FakeMemcacheClient(object):

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key, None)

    def set(self, key, value):
        self.values[key] = value


class TestWSGIApp(unittest.TestCase):

    def setUp(self):
        config_dict = {"configuration": "file:" + BASE_CONFIG_FILE}
        self.app = wsgiapp.make_app(config_dict).app

    def tearDown(self):
        for storage in self.app.storages.itervalues():
            sqlfile = storage.sqluri.split('sqlite:///')[-1]
            if os.path.exists(sqlfile):
                os.remove(sqlfile)

    def test_host_specific_config(self):
        class request:
            host = "localhost"
        sqluri = self.app.get_storage(request).sqluri
        assert sqluri.startswith("sqlite:////tmp/test-sync-storage")

        request.host = "some-test-host"
        sqluri = self.app.get_storage(request).sqluri
        assert sqluri.startswith("sqlite:////tmp/test-storage-host1")

        request.host = "another-test-host"
        sqluri = self.app.get_storage(request).sqluri
        assert sqluri.startswith("sqlite:////tmp/test-storage-host2")

    def test_dependant_options(self):
        config = dict(self.app.config)
        config['storage.check_node_status'] = True
        old_client = wsgiapp.Client
        wsgiapp.Client = None
        # make sure the app cannot be initialized if it's asked
        # to check node status and memcached is not present
        try:
            self.assertRaises(ValueError, wsgiapp.make_app, config)
        finally:
            wsgiapp.Client = old_client

    def test_checking_node_status_in_memcache(self):
        app = self.app
        app.cache = FakeMemcacheClient()
        app.check_node_status = True
        testclient = TestApp(self.app, extra_environ={
            "HTTP_HOST": "some-test-host",
        })

        # With no node data in memcache, requests to known nodes should
        # succeed while requests to unknown nodes should fail.
        testclient.get("/__heartbeat__", headers={"Host": "some-test-host"},
                       status=200)
        testclient.get("/__heartbeat__", headers={"Host": "unknown-host"},
                       status=503)

        # Marking the node as "backoff" will succeed, but send backoff header.
        app.cache.set("status:some-test-host", "backoff")
        r = testclient.get("/__heartbeat__", status=200)
        self.assertEquals(r.headers["X-Weave-Backoff"], str(app.retry_after))

        app.cache.set("status:some-test-host", "backoff:100")
        r = testclient.get("/__heartbeat__", status=200)
        self.assertEquals(r.headers["X-Weave-Backoff"], "100")

        # Marking the node as "down", "draining" or "unhealthy" will result
        # in a 503 response with backoff header.
        app.cache.set("status:some-test-host", "down")
        r = testclient.get("/__heartbeat__", status=503)
        self.assertEquals(r.headers["X-Weave-Backoff"], str(app.retry_after))
        self.assertEquals(r.headers["Retry-After"], str(app.retry_after))

        app.cache.set("status:some-test-host", "draining")
        r = testclient.get("/__heartbeat__", status=503)
        self.assertEquals(r.headers["X-Weave-Backoff"], str(app.retry_after))
        self.assertEquals(r.headers["Retry-After"], str(app.retry_after))

        app.cache.set("status:some-test-host", "unhealthy")
        r = testclient.get("/__heartbeat__", status=503)
        self.assertEquals(r.headers["X-Weave-Backoff"], str(app.retry_after))
        self.assertEquals(r.headers["Retry-After"], str(app.retry_after))

        # A nonsense node status will be ignored.
        app.cache.set("status:some-test-host", "nonsensical-value")
        r = testclient.get("/__heartbeat__", status=200)
        self.assertTrue("X-Weave-Backoff" not in r.headers)

        # Node status only affects the node that it belongs to.
        app.cache.set("status:some-test-host", "unhealthy")
        r = testclient.get("/__heartbeat__",
                           headers={"Host": "another-test-host"},
                           status=200)
        self.assertTrue("X-Weave-Backoff" not in r.headers)


class TestEOLHeaders(unittest.TestCase):

    BASE_CONFIG = {
        "configuration": "file:" + BASE_CONFIG_FILE,
    }

    def setUp(self):
        self.app = None
        self.testclient = None

    def tearDown(self):
        if self.app is not None:
            for storage in self.app.storages.itervalues():
                sqlfile = storage.sqluri.split('sqlite:///')[-1]
                if os.path.exists(sqlfile):
                    os.remove(sqlfile)

    def _set_config(self, custom_config, extra_environ={}):
        config = self.BASE_CONFIG.copy()
        config.update(custom_config)
        self.app = wsgiapp.make_app(config).app
        self.testclient = TestApp(self.app, extra_environ=extra_environ)

    def _create_user(self, username, password=None):
        if password is None:
            password = username
        email = username + "@example.com"
        authz = base64.encodestring("%s:%s" % (username, password)).strip()
        assert self.app.auth.backend.create_user(username, password, email)
        return {
            "username": username,
            "password": password,
            "uid": self.app.auth.backend.get_user_id(username),
            "authz": "Basic " + authz,
        }

    def test_headers_are_not_sent_by_default(self):
        self._set_config({})
        # This should never get headers; check that it doesn't explode.
        r = self.testclient.get("/__heartbeat__")
        self.assertTrue("X-Weave-Alert" not in r.headers)
        # Nobody should see EOL headers until we switch them on.
        user = self._create_user("test1")
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)

    def test_headers_are_sent_in_general_release(self):
        self._set_config({
            "storage.eol_rollout_percent": 100,
            "storage.eol_general_release": True,
        })
        user = self._create_user("test1")
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
        })
        eol = json.loads(r.headers["X-Weave-Alert"])
        self.assertEqual(eol["code"], "soft-eol")

    def test_headers_are_sent_to_rollout_percentage(self):
        ROLLOUT_PERCENT = random.randint(0, 100)
        self._set_config({
            "storage.eol_rollout_percent": ROLLOUT_PERCENT,
            "storage.eol_general_release": True,
        })
        eol_count = 0
        for uid in xrange(100):
            user = self._create_user("test%d" % (uid,))
            r = self.testclient.get("/1.0/test%d/info/collections" % (uid,),
                                    headers={ "Authorization": user["authz"] })
            try:
                eol = json.loads(r.headers["X-Weave-Alert"])
            except KeyError:
                pass
            else:
                self.assertEqual(eol["code"], "soft-eol")
                eol_count += 1
        self.assertEquals(eol_count, ROLLOUT_PERCENT)

    def test_headers_are_restricted_before_general_release(self):
        self._set_config({
            "storage.eol_rollout_percent": 100,
            "storage.eol_general_release": False,
        })
        user = self._create_user("test1")
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "Firefox/36.1 FxSync/1.39.0.20141211102843.desktop"
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "Firefox-Android-FxAccounts/37.0a1 (Nightly)"
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "WackyThirdPartySyncClient"
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)
        # A recent-enough desktop firefox, this one gets the EOL header.
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.20141211102843.desktop"
        })
        eol = json.loads(r.headers["X-Weave-Alert"])
        self.assertEqual(eol["code"], "soft-eol")
        # Unless there are multiple clients associated with the account.
        storage = self.app.storages["default"]
        storage.set_items(user["uid"], "clients", [
            { "id": "client1", "payload": "desktop firefox" },
        ])
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.20141211102843.desktop"
        })
        eol = json.loads(r.headers["X-Weave-Alert"])
        self.assertEqual(eol["code"], "soft-eol")
        storage.set_items(user["uid"], "clients", [
            { "id": "client2", "payload": "firefox for android" },
        ])
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.20141211102843.desktop"
        })
        self.assertTrue("X-Weave-Alert" not in r.headers)

    def test_rollout_percentage_works_before_general_release(self):
        ROLLOUT_PERCENT = random.randint(0, 100)
        self._set_config({
            "storage.eol_rollout_percent": ROLLOUT_PERCENT,
            "storage.eol_general_release": "false",
        })
        eol_count = 0
        for uid in xrange(100):
            user = self._create_user("test%d" % (uid,))
            url = "/1.0/test%d/info/collections" % (uid,)
            r = self.testclient.get(url, headers={
                "Authorization": user["authz"],
            })
            self.assertTrue("X-Weave-Alert" not in r.headers)
            r = self.testclient.get(url, headers={
                "Authorization": user["authz"],
                "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
            })
            try:
                eol = json.loads(r.headers["X-Weave-Alert"])
            except KeyError:
                pass
            else:
                self.assertEqual(eol["code"], "soft-eol")
                eol_count += 1
        self.assertEquals(eol_count, ROLLOUT_PERCENT)

    def test_eol_header_fields_are_configurable(self):
        self._set_config({
            "storage.eol_rollout_percent": 100,
            "storage.eol_general_release": True,
            "storage.eol_header_code": "hard-eol",
            "storage.eol_header_url": "https://example.com/buh-bye-to-sync",
            "storage.eol_header_message": "sync has sunk",
        })
        user = self._create_user("test1")
        r = self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user["authz"],
        })
        eol = json.loads(r.headers["X-Weave-Alert"])
        self.assertEqual(eol["code"], "hard-eol")
        self.assertEqual(eol["url"], "https://example.com/buh-bye-to-sync")
        self.assertEqual(eol["message"], "sync has sunk")

    def test_eol_header_is_sent_after_reducing_rollout_percent(self):
        self._set_config({
            "storage.eol_rollout_percent": 24,
            "storage.eol_rollout_percent_hwm": 35,
            "storage.eol_general_release": "true",
        })
        # Make even-numbered users appear to have started migration.
        storage = self.app.storages["default"]
        for uid in xrange(100):
            if uid % 2 == 0:
                storage.set_item(uid, "meta", "fxa_credentials", {
                    "payload": "FOO"
                })
        # The even-numbered users below high-water-mark should see EOL headers.
        for uid in xrange(100):
            user = self._create_user("test%d" % (uid,))
            url = "/1.0/test%d/info/collections" % (uid,)
            r = self.testclient.get(url, headers={
                "Authorization": user["authz"],
            })
            if user["uid"] < 24 or user["uid"] == 100:
                self.assertTrue("X-Weave-Alert" in r.headers)
            elif user["uid"] < 35 and user["uid"] % 2 == 0:
                self.assertTrue("X-Weave-Alert" in r.headers)
            else:
                self.assertTrue("X-Weave-Alert" not in r.headers)

    def test_migration_metrics_collection(self):
        self._set_config({
            "storage.eol_rollout_percent": 3,
            "storage.eol_general_release": False,
        })
        user1 = self._create_user("test1")
        user2 = self._create_user("test2")
        user3 = self._create_user("test3")
        self.assertTrue(user1["uid"] == 1)
        self.assertTrue(user2["uid"] == 2)
        self.assertTrue(user3["uid"] == 3)
        # This should get an EOL header.
        self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user1["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
        })
        # So should this.
        self.testclient.get("/1.0/test2/info/collections", headers={
            "Authorization": user2["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
        })
        # This should not, due to uid above the rollout percentage.
        self.testclient.get("/1.0/test3/info/collections", headers={
            "Authorization": user3["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
        })
        # This should not be considered, due to ineligible user agent.
        self.testclient.get("/1.0/test1/info/collections", headers={
            "Authorization": user1["authz"],
            "User-Agent": "Firefox/36.1 FxSync/1.39.0.desktop"
        })
        # Simulate a user access the migration sentinel across several devices.
        # This should count as one write and two reads.
        # The first two should also get EOL headers sent.
        self.testclient.put("/1.0/test1/storage/meta/fxa_credentials", "{}",
            headers={
                "Authorization": user1["authz"],
                "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
            }
        )
        self.testclient.get("/1.0/test1/storage/meta/fxa_credentials",
            headers={
                "Authorization": user1["authz"],
                "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
            }
        )
        self.testclient.get("/1.0/test1/storage/meta/fxa_credentials",
            headers={
                "Authorization": user1["authz"],
                "User-Agent": "Fennec/1.2.3"
            }
        )
        # Simulate migrated clients cleaning up their client records.
        # Only the eligible desktop device should count.
        self.testclient.delete("/1.0/test1/storage/clients/desktop", headers={
            "Authorization": user1["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
        })
        self.testclient.delete("/1.0/test1/storage/clients/mobile", headers={
            "Authorization": user1["authz"],
            "User-Agent": "Fennec/1.2.3"
        })
        # This delete should not be counted, due to uid above rollout percent.
        self.testclient.delete("/1.0/test3/storage/clients/desktop", headers={
            "Authorization": user3["authz"],
            "User-Agent": "Firefox/37.0a1 FxSync/1.39.0.desktop"
        })
        # OK, let's see if we got all the counts correct.
        counts = collections.defaultdict(lambda: 0)
        for msg in self.app.logger.sender.msgs:
            msg = json.loads(msg)
            if msg.get("type") == "counter":
                counts[msg["fields"]["name"]] += int(msg["payload"])
        self.assertEqual(counts[wsgiapp.CTR_EOL_HEADER_CONSIDERED], 7)
        self.assertEqual(counts[wsgiapp.CTR_EOL_HEADER_SENT], 5)
        self.assertEqual(counts[wsgiapp.CTR_EOL_SENTINEL_READ], 2)
        self.assertEqual(counts[wsgiapp.CTR_EOL_SENTINEL_WRITE], 1)
        self.assertEqual(counts[wsgiapp.CTR_EOL_CLIENT_DELETE], 1)
