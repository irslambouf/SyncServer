#!/usr/bin/python

# Tests that exercise the basic functions of the server.

# Implementations of well-known or specified protocols are contained elsewhere.
# These tests only exercise those functions that are specific to the
# implementation of the server.
import threading
import random
import base64
import logging
import urllib2
import httplib
import hashlib
import unittest
import time
import struct
import json
import string
from base64 import b64encode, b32encode
from decimal import Decimal
from hashlib import sha1

opener = urllib2.build_opener(urllib2.HTTPHandler)

import weave

# Import configuration
import test_config


_CHARS = string.ascii_letters + string.digits


def randid(size=4, chars=_CHARS):
    return ''.join([random.choice(chars) for i in range(size)])


def round_time(value, drift=.01):
    """Rounds a timestamp to the next two digits"""
    if not isinstance(value, float):
        value = float(value)
    return round(value, 2) + drift


class TestAccountManagement(unittest.TestCase):


    def setUp(self):
        self.users = []

    def tearDown(self):
        failures = []
        for user_id, password in self.users:
            try:
                weave.deleteUser(test_config.SERVER_BASE, user_id, password,
                                 withHost=test_config.HOST_NAME)
            except weave.WeaveException, e:
                failures.append(user_id)
        if len(failures) > 0:
            raise weave.WeaveException('Could not delete those users: %s' % \
                                 ', '.join(failures))


    def _rand_uid_email(self):
        email = ('weaveunittest_' + randid(size=10, chars=string.lowercase) +
                '@mozilla.com')
        hashed = sha1(email).digest()
        return b32encode(hashed).lower(), email

    def _randuser(self):
        return 'weaveunittest_' + randid(size=10, chars=string.lowercase)

    # XXX sreg/reg refactoring
    def _testPasswordReset(self):
        root_url = '%s/user/1.0/' % test_config.SERVER_BASE

        user_id, email = self._rand_uid_email()
        while not weave.checkNameAvailable(test_config.SERVER_BASE, user_id,
                                           withHost=test_config.HOST_NAME):
            user_id, email = self._rand_uid_email()

        # unknown user
        req = urllib2.Request("%s/%s/password_reset" % (root_url, user_id))
        try:
            f = opener.open(req)
            f.read()
        except urllib2.HTTPError, e:
            self.assertEqual(e.read(), '3')
        else:
            raise AssertionError()

        # existing user, no captcha
        user_id = self._create_user()
        req = urllib2.Request("%s/%s/password_reset" % (root_url, user_id))
        try:
            f = opener.open(req)
            result = f.read()
        except urllib2.HTTPError, e:
            self.assertEqual(e.read(), '12')
        else:
            # seems that the server is not enabled for captcha
            self.assertEqual(result, 'success')

        # XXX Need to test with captcha

    def _create_user(self, email='testuser@test.com',
                     password='testuser@test.com'):
        user_id = email = None
        while True:
            user_id, email = self._rand_uid_email()
            if not weave.checkNameAvailable(test_config.SERVER_BASE, user_id,
                                            withHost=test_config.HOST_NAME):
                continue
            weave.createUser(test_config.SERVER_BASE, user_id, password, email,
                             withHost=test_config.HOST_NAME,
                             secret=test_config.SECRET)
            break
        self.users.append((user_id, password))
        return user_id

    def testAccountManagement2(self):

        if test_config.USERNAME:
            return


        email = 'testuser@test.com'
        password = 'mypassword'
        userID = self._create_user(email, password)

        # Change the email address
        newEmail = 'changed@test.com'
        weave.changeUserEmail(test_config.SERVER_BASE, userID, password,
                              newEmail, withHost=test_config.HOST_NAME)
        # With wrong password
        try:
            weave.changeUserEmail(test_config.SERVER_BASE, userID, "wrongPassword",
                                  "shouldnotwork@test.com", withHost=test_config.HOST_NAME)
            self.fail("Should have failed to change email with wrong password")
        except weave.WeaveException:
            pass


    def test_several_users(self):
        # this will create 100 users, that will connect, change their password
        # in parallel. This test ensures that the ldap connectors behaves as
        # expected
        class Worker(threading.Thread):
            def __init__(self):
                threading.Thread.__init__(self)
                self.server = test_config.SERVER_BASE
                self.host = test_config.HOST_NAME
                self.password = 'mypassword'
                self.email = 'test@weavetest.com'
                self.user_id = self._create_user()
                storage = weave.getUserStorageNode(self.server, self.user_id,
                                                   self.password, withHost=self.host)
                self.storage = storage.rstrip('/')

            def _create_user(self):
                while True:
                    user_id = 'weaveunittest_' + randid(size=10,
                                                      chars=string.lowercase)
                    if not weave.checkNameAvailable(self.server, user_id,
                            withHost=self.host):
                        continue

                    # create the user
                    weave.createUser(self.server, user_id, self.password,
                                     self.email,
                                     withHost=self.host,
                                     secret=test_config.SECRET)
                    break
                return user_id

            def _create_wbo(self):
                wboid = randid(size=10, chars=string.lowercase)
                wbo = {'id': wboid, 'payload': 'aPayload'}
                weave.add_or_modify_item(self.storage, self.user_id,
                                         self.password, 'coll', wbo,
                                         withHost=self.host)

            def run(self):
                try:
                    # creating objects
                    for i in range(5):
                        self._create_wbo()

                    # changing the password
                    new = 'mynewpassword'
                    weave.changeUserPassword(self.server, self.user_id,
                                            self.password, new,
                                            withHost=self.host)

                    # trying the old password, should fail
                    try:
                        weave.changeUserEmail(self.server, self.user_id,
                                              self.password,
                                              "shouldnotwork@test.com",
                                              withHost=self.host)
                    except weave.WeaveException:
                        pass
                    else:
                        raise Exception('Should have raised')

                    self.password = new

                    # creating objects again
                    for i in range(5):
                        self._create_wbo()

                    # deleting the account
                    weave.deleteUser(self.server, self.user_id, self.password,
                                    withHost=self.host)
                    self.error = None

                except Exception, error:
                    self.error = error

        workers = [Worker() for i in range(50)]

        for worker in workers:
            worker.start()

        for worker in workers:
            worker.join()

        errors = [worker.error for worker in workers
                  if worker.error is not None]

        # raising the first one for now
        if len(errors) > 0:
            raise errors[0]


    def testAccountManagement(self):
        if test_config.USERNAME:
            # If we have a username, we're running against a production server
            # and don't want to create new accounts.  Just return silently for now.
            return

        password = 'mypassword'
        while True:
            userID, email = self._rand_uid_email()

            if not weave.checkNameAvailable(test_config.SERVER_BASE, userID, withHost=test_config.HOST_NAME):
                continue
            # Create a user
            weave.createUser(test_config.SERVER_BASE, userID, password,
                             email, withHost=test_config.HOST_NAME,
                             secret=test_config.SECRET)
            break

        # NOTE that we currently have no way of testing that email address persisted correctly

        # Name should now be unavailable
        self.failIf(weave.checkNameAvailable(test_config.SERVER_BASE, userID, withHost=test_config.HOST_NAME))

        # Storage node
        try:
            storageNode = weave.getUserStorageNode(test_config.SERVER_BASE, userID, password, withHost=test_config.HOST_NAME)
            self.failIf(storageNode == None)
        except weave.WeaveException:
            # if we don't have one, use the same node
            storageNode = test_config.SERVER_BASE

        # Change the email address
        newEmail = 'changed@test.com'
        weave.changeUserEmail(test_config.SERVER_BASE, userID, password, newEmail, withHost=test_config.HOST_NAME)

        # With wrong password
        try:
            weave.changeUserEmail(test_config.SERVER_BASE, userID, "wrongPassword", "shouldnotwork@test.com", withHost=test_config.HOST_NAME)
            self.fail("Should have failed to change email with wrong password")
        except weave.WeaveException:
            pass

        return

        # XXX need the SREG new imple
        # Change the password
        newPassword = 'mynewpassword'
        weave.changeUserPassword(test_config.SERVER_BASE, userID, password, newPassword, withHost=test_config.HOST_NAME)

        # This doesn't actually check anything because we don't use the password for getUserStorageNode
        storageNode = weave.getUserStorageNode(test_config.SERVER_BASE, userID, newPassword, withHost=test_config.HOST_NAME)
        self.failIf(storageNode == None)

        # TODO Exercise Weave-Password-Reset feature


        # With wrong password
        try:
            weave.changeUserPassword(test_config.SERVER_BASE, userID, "shouldnotwork", newPassword, withHost=test_config.HOST_NAME)
            self.fail("Should have failed to change password with wrong password")
        except weave.WeaveException:
            pass

        # Can I change my email?  This proves that the password change worked.
        anotherNewEmail = 'changedagain@test.com'
        weave.changeUserEmail(test_config.SERVER_BASE, userID, newPassword, anotherNewEmail, withHost=test_config.HOST_NAME)

        # Delete with wrong password
        try:
            weave.deleteUser(test_config.SERVER_BASE, userID, "wrongPassword", withHost=test_config.HOST_NAME)
            self.fail("Should have failed to delete user with wrong password")
        except weave.WeaveException:
            pass

        # Delete
        # This isn't the right test - in a non-sharded configuration
        # we always get a 404 for storage node
        weave.deleteUser(test_config.SERVER_BASE, userID, newPassword, withHost=test_config.HOST_NAME)
#       self.failUnless(weave.checkNameAvailable(test_config.SERVER_BASE, userID, withHost=test_config.HOST_NAME))
#       try:
#           storageNode = weave.getUserStorageNode(test_config.SERVER_BASE, userID, newPassword, withHost=test_config.HOST_NAME)
#           self.fail("Should have failed to get user storage node after delete")
#       except weave.WeaveException:
#           pass


    # TODO: Test UTF-8 encoded names; they should work

    def testBoundaryCases(self):

        if test_config.USERNAME:
            # If we have a username, we're running against a production server
            # and don't want to create new accounts.  Just return silently for now.
            return


        # Bad usernames
        for i in (range(ord(' ')+1, ord('0')-1) +
                            range(ord('9')+1, ord('A')-1) +
                            range(ord('Z')+1, ord('a')-1) +
                            range(ord('z')+1, 127)):
            if chr(i) == '"': continue
            if chr(i) == '-': continue
            if chr(i) == '.': continue
            if chr(i) == '_': continue
            if chr(i) == '#': continue # technically this is okay, since the name just gets split at the '#'
            if chr(i) == '/': continue # technically this is okay, since the name just gets split at the '/'
            if chr(i) == '?': continue # technically this is okay, since the name just gets split at the '?'

            try:
                self.failIf(weave.checkNameAvailable(test_config.SERVER_BASE, "badcharactertest" + chr(i), withHost=test_config.HOST_NAME),
                    "checkNameAvailable should return error for name containing '%s' character" % chr(i))
            except weave.WeaveException, e:
                pass

            try:
                self.failIf(weave.createUser(test_config.SERVER_BASE,
                    "badcharactertest" + chr(i), "ignore", "ignore",
                   withHost=test_config.HOST_NAME, secret=test_config.SECRET),
                    "createUser should throw error for name containing '%s' character" % chr(i))
                self.fail("Should have failed with bad username")
            except weave.WeaveException, e:
                pass

        try:
            veryLongName = "VeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryVeryLongUsername"
            weave.createUser(test_config.SERVER_BASE, veryLongName, "password", "ignore",
                    withHost=test_config.HOST_NAME, secret=test_config.SECRET)
            self.fail("Should have failed with bad (too long) user name")
        except:
            pass

class TestStorage(unittest.TestCase):

    def setUp(self):
        self.userList = []
        self.email = 'testuser@test.com'

        if test_config.USERNAME:
            # Specified username: hard-code it, and clear out any old records

            if not test_config.PASSWORD:
                raise ValueError("If username is provided, a password must also be provided")
            self.userID = test_config.USERNAME
            self.password = test_config.PASSWORD
            self.storageServer =  weave.getUserStorageNode(test_config.SERVER_BASE,
                    self.userID, self.password, withHost=test_config.HOST_NAME)
            self.storageServer = self.storageServer.rstrip('/')

            #if test_config.STORAGE_SCHEME and test_config.STORAGE_SERVER:
            #    self.storageServer = "%s://%s" % (test_config.STORAGE_SCHEME, test_config.STORAGE_SERVER)

            weave.delete_all(self.storageServer, self.userID, self.password, withHost=test_config.HOST_NAME)

        else:
            self.password = 'mypassword'

            self.reuseUser = True
            if self.reuseUser:
                while True:
                    self.userID = 'weaveunittest_' + ''.join([chr(random.randint(ord('a'), ord('z'))) for i in xrange(10)])
                    if not weave.checkNameAvailable(test_config.SERVER_BASE, self.userID, withHost=test_config.HOST_NAME):
                        continue
                    weave.createUser(test_config.SERVER_BASE, self.userID, self.password,
                            self.email, withHost=test_config.HOST_NAME,
                            secret=test_config.SECRET)
                    break
                self.storageServer = weave.getUserStorageNode(test_config.SERVER_BASE, self.userID, self.password, withHost=test_config.HOST_NAME)
                self.storageServer = self.storageServer.rstrip('/')
                self.userList.append((self.userID, self.storageServer))

    def tearDown(self):
        for user, server in self.userList:
            weave.delete_all(server, user, self.password, withHost=test_config.HOST_NAME)
            weave.deleteUser(test_config.SERVER_BASE, user, self.password, withHost=test_config.HOST_NAME)

    def failUnlessObjsEqualWithDrift(self, o1, o2):
        "Helper function to compare two maps; the 'modified' field is compared with almostEqual"
        for key, value in o1.items():
            if not key in o2:
                self.fail("%s != %s (%s)" % (str(o1), str(o2), key))
            if key == "modified":
                self.failUnlessAlmostEqual(float(value), float(o2['modified']))
            else:
                if value != o2[key]:
                    self.fail("%s != %s (%s)" % (str(o1), str(o2), key))
        for key in o2.keys():
            if not key in o1:
                self.fail("%s != %s (%s)" % (str(o1), str(o2), key))


    def createCaseUser(self, forceNewUser=False):
        "Helper function to create a new user; returns the userid and storageServer node"
        if test_config.USERNAME:
            if forceNewUser:
                self.fail("ForceNewUser isn't supported against production servers")

            try:
                collections = weave.get_collection_timestamps(self.storageServer,
                        self.userID, self.password, withHost=test_config.HOST_NAME)
            except weave.WeaveException:
                pass
            else:
                if len(collections):
                    for c in collections.keys():
                        weave.delete_items(self.storageServer, self.userID,
                                self.password, c, withHost=test_config.HOST_NAME)

            return self.userID, self.storageServer

        if forceNewUser or not self.reuseUser:
            while True:
                userID = 'weaveunittest_' + ''.join([chr(random.randint(ord('a'), ord('z'))) for i in xrange(10)])
                if not weave.checkNameAvailable(test_config.SERVER_BASE, userID, withHost=test_config.HOST_NAME):
                    continue
                weave.createUser(test_config.SERVER_BASE, userID, self.password,
                        self.email, withHost=test_config.HOST_NAME,
                        secret=test_config.SECRET)
                break

            storageServer = weave.getUserStorageNode(test_config.SERVER_BASE, userID, self.password, withHost=test_config.HOST_NAME)
            storageServer = storageServer.rstrip('/')
            self.userList.append((userID, storageServer))
            return (userID, storageServer)
        else:
            # Clear out old objects
            try:
                collections = weave.get_collection_timestamps(self.storageServer, self.userID, self.password, withHost=test_config.HOST_NAME)
            except weave.WeaveException:
                pass
            else:
                if len(collections):
                    for c in collections.keys():
                        weave.delete_items(self.storageServer, self.userID, self.password, c, withHost=test_config.HOST_NAME)
            return (self.userID, self.storageServer)

    def testAdd(self):
        "testAdd: An object can be created with all optional parameters, and everything persists correctly."
        userID, storageServer = self.createCaseUser()
        oid = randid(8)

        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll',
                {'id': oid, 'sortindex':3, 'parentid':'dearolddad',
                 'predecessorid':'bigbrother', 'payload':'ThisIsThePayload'},
                withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll',
                                oid, withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id': oid,
                'payload':'ThisIsThePayload', 'modified':float(ts),
                'sortindex':3, 'parentid':'dearolddad', 'predecessorid':'bigbrother'})

    def testAdd_IDFromURL(self):
        "testAdd_IDFromURL: An object can be created with an ID from the URL, with no ID in the provided payload"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload'}, urlID='thisIsMyID', withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', 'thisIsMyID', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'thisIsMyID', 'payload':'ThisIsThePayload', 'modified':float(ts)})

    def helper_addIDFromURL_UnusualCharactersHelper(self, specialChar):
        "Helper function: Exercises adding an object with an unusual character in the URL"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload'}, urlID='abc%sdef' % specialChar, withHost=test_config.HOST_NAME)
        except weave.WeaveException, e:
            # if we throw, that's fine
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error' was %s" % e)
            return

        # If we don't throw, getting it should work
        try:
            result = weave.get_item(storageServer, userID, self.password, 'coll', 'abc%sdef' % specialChar, withHost=test_config.HOST_NAME)
            self.failUnlessObjsEqualWithDrift(result, {'id':'abc%sdef' % specialChar, 'payload':'ThisIsThePayload', 'modified':float(ts)})
        except weave.WeaveException, e:
            self.fail("Error while retrieving object with a '%s' in the ID: %s" % (specialChar, e))

    def testAdd_IDFromURL_Hash(self):
        "testAdd_IDFromURL_Hash: An object can be created with an ID from a URL containing a hash mark, and retrieved"
        self.helper_addIDFromURL_UnusualCharactersHelper("#")

    def testAdd_IDFromURL_QMark(self):
        "testAdd_IDFromURL_Hash: An object can be created with an ID from a URL containing a question mark, and retrieved"
        self.helper_addIDFromURL_UnusualCharactersHelper("?")

    def testAdd_IDFromURL_Tilde(self):
        "testAdd_IDFromURL_Tilde: An object can be created with an ID from a URL containing a tilde, and retrieved"
        self.helper_addIDFromURL_UnusualCharactersHelper("~")

    def testAdd_SlashID(self):
        "testAdd_SlashID: An object can be created with slashes in the ID, and subsequently retrieved, OR the ID should be forbidden"
        userID, storageServer = self.createCaseUser()
        # XXX
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload', 'id':'abc/def'}, withHost=test_config.HOST_NAME)
        except weave.WeaveException, e:
            # if we throw, that's fine
            self.failUnless(str(e).find("400") > 0, "Should have been an HTTP 400 error' was %s" % e)
            return

        # If we don't throw, getting it should work
        try:
            result = weave.get_item(storageServer, userID, self.password, 'coll', 'abc/def', withHost=test_config.HOST_NAME)
            self.failUnlessObjsEqualWithDrift(result, {'id':'abc/def', 'payload':'ThisIsThePayload', 'modified':float(ts)})
        except weave.WeaveException, e:
            self.fail("Error while retrieving object with a slash in the ID: %s" % e)

    def testAdd_HashID(self):
        "testAdd_HashID: An object can be created with hashes in the ID, and subsequently retrieved, OR the ID should be forbidden"
        userID, storageServer = self.createCaseUser()

        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload', 'id':'abc#def'}, withHost=test_config.HOST_NAME)
        except weave.WeaveException, e:
            # if we throw, that's fine
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error' was %s" % e)
            return

        # If we don't throw, getting it should work
        try:
            result = weave.get_item(storageServer, userID, self.password, 'coll', 'abc#def', withHost=test_config.HOST_NAME)
            self.failUnlessObjsEqualWithDrift(result, {'id':'abc#def', 'payload':'ThisIsThePayload', 'modified':float(ts)})
        except weave.WeaveException, e:
            self.fail("Error while retrieving object with a hash in the ID: %s" % e)

    def testAdd_QMarkID(self):
        "testAdd_QMarkID: An object can be created with a question mark in the ID, and subsequently retrieved, OR the ID should be forbidden"
        userID, storageServer = self.createCaseUser()

        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload', 'id':'abc?def'}, withHost=test_config.HOST_NAME)
        except weave.WeaveException, e:
            # if we throw, that's fine
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error' was %s" % e)
            return

        # If we don't throw, getting it should work
        try:
            result = weave.get_item(storageServer, userID, self.password, 'coll', 'abc?def', withHost=test_config.HOST_NAME)
            self.failUnlessObjsEqualWithDrift(result, {'id':'abc?def', 'payload':'ThisIsThePayload', 'modified':float(ts)})
        except weave.WeaveException, e:
            self.fail("Error while retrieving object with a question mark in the ID: %s" % e)


    def testAdd_IfUnmodifiedSince_NotModified(self):
        "testAdd_IfUnmodifiedSince_NotModified: If an IfUnmodifiedSince header is provided, and the collection has not been changed, an attempt succeeds."
        userID, storageServer = self.createCaseUser()
        oid = randid()

        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll',
                {'id': oid, 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        time.sleep(.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password,
                                       'coll', {'id': oid,
                                                'payload':'ThisIsThePayload'},
                                       ifUnmodifiedSince=round_time(ts), withHost=test_config.HOST_NAME)

        result = weave.get_item(storageServer, userID, self.password, 'coll',
                                oid, withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result,
                                          {'id': oid,
                                           'payload': 'ThisIsThePayload',
                                           'modified': float(ts2)})

    def testAdd_IfUnmodifiedSince_Modified(self):
        "testAdd_IfUnmodifiedSince_Modified: If an IfUnmodifiedSince header is provided, and the collection has changed, the attempt fails."
        userID, storageServer = self.createCaseUser()
        oid = randid()
        ts = weave.add_or_modify_item(storageServer, userID, self.password,
                                      'coll',
                                      {'id': oid,
                                       'payload':'ThisIsThePayload'},
                                      withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password,
                                       'coll', {'id': oid,
                                                'payload': 'ThisIsThePayload'},
                                       withHost=test_config.HOST_NAME)
        try:
            ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll',
                                           {'id': oid, 'payload':'ThisIsThePayload'},
                                           ifUnmodifiedSince=round_time(ts), withHost=test_config.HOST_NAME)
            self.fail("Attempt to add an item when the collection had changed after the ifModifiedSince time should have failed")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("412") > 0, "Should have been an HTTP 412 error")

    def testAdd_NoIDOrPayload(self):
        "testAdd_NoIDOrPayload: Attempts to create an object with no ID or payload do not work."
        # Empty payload is fine
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {}, withHost=test_config.HOST_NAME)
            self.fail("Attempt to add an item when the collection had changed after the ifModifiedSince time should have failed")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400") > 0, "Should have been an HTTP 400 error")

    def testAdd_EmptyPayload(self):
        "testAdd_EmptyPayload: Attempts to create an object with a zero-length payload work correctly."
        # Empty payload is fine
        userID, storageServer = self.createCaseUser()
        oid = randid(8)
        ts = weave.add_or_modify_item(storageServer, userID, self.password,
                                      'coll',
                                      {'id': oid, 'payload': ''},
                                      withHost=test_config.HOST_NAME)

        result = weave.get_item(storageServer, userID, self.password, 'coll',
                                oid, withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result,
                                          {'id': oid, 'payload': '',
                                           'modified':float(ts)})

    def testAdd_EmptyCollection(self):
        "testAdd_EmptyCollection: Attempts to create an object without a collection report an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, '',
                    {'id': randid(),'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            self.fail("Should have reported error with zero-length collection")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("404") > 0, "Should have been an HTTP 404 error")

    def testAdd_MissingID(self):
        "testAdd_MissingID: Attempts to create an object without an ID report an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            self.fail("Should have reported error with missing ID")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400") > 0, "Should have been an HTTP 400 error")

    def testAdd_NullIDCharacter(self):
        "testAdd_NullIDCharacter: Null bytes are legal in objectIDs, and objects can be retrieved using them"
        userID, storageServer = self.createCaseUser()
        id = '123\\0000123'
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':id, 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', id, withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'123\\0000123', 'payload':'ThisIsThePayload', 'modified':float(ts)})

    # There are no forbidden characters in an ID right now - VARBINARY
    def skiptestAdd_UnusualIDCharacters(self):
        "testAdd_UnusualIDCharacters: All bytes values from 01 to 255 are legal in an object ID"
        userID, storageServer = self.createCaseUser()
        for i in range(1,256):
            id = '123\\00' + chr(i).encode("hex")
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':id, 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            result = weave.get_item(storageServer, userID, self.password, 'coll', id, withHost=test_config.HOST_NAME)
            self.failUnlessObjsEqualWithDrift(result, {'id':id, 'payload':'ThisIsThePayload', 'modified':float(ts)})

    def skiptestAdd_UnusualParentIDCharacters(self):
        "testAdd_UnusualParentIDCharacters: All bytes values from 00 to 255 are legal in a parent ID"
        userID, storageServer = self.createCaseUser()
        for i in range(0,256):
            id = '123\\00' + chr(i).encode("hex")
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'parentid':id, 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)

    def skiptestAdd_UnusualPredecessorIDCharacters(self):
        "testAdd_UnusualPredecessorIDCharacters: All bytes values from 00 to 255 are legal in a predecessor ID"
        userID, storageServer = self.createCaseUser()
        for i in range(0,256):
            id = '123\\00' + chr(i).encode("hex")
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'predecessorid': id, 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)

    def testAdd_IDTooBig(self):
        "testAdd_IDTooBig: An ID longer than 64 bytes should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234567890123456789012345678901234567890123456789012345678901234567890', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            self.fail("Should have reported error with too-big ID")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error")

    def testAdd_ParentIDTooBig(self):
        "testAdd_ParentIDTooBig: A parentID longer than 64 bytes should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'parentid':'1234567890123456789012345678901234567890123456789012345678901234567890', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            self.fail("Should have reported error with too-big parentID")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error")

    def testAdd_PredecessorIDTooBig(self):
        "testAdd_PredecessorIDTooBig: A predecessorID longer than 64 bytes should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'predecessorid':'1234567890123456789012345678901234567890123456789012345678901234567890', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            self.fail("Should have reported error with too-big predecessorID")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error")

    def testAdd_NonNumericSortIndex(self):
        "testAdd_NonNumericSortIndex: A non-numeric sortindex should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':'abc', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            result = weave.get_item(storageServer, userID, self.password, 'coll', '1234')
            self.fail("Should have reported error with non-numeric SortIndex: got back %s" % result)
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error")

    def testAdd_TooBigSortIndex(self):
        "testAdd_TooBigSortIndex: A sortindex longer than 11 bytes should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':'1234567890123', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            result = weave.get_item(storageServer, userID, self.password, 'coll', '1234')
            self.fail("Should have reported error with too-big SortIndex: got back %s" % result)
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error: was %s" % e)

    def testAdd_TooSmallSortIndex(self):
        "testAdd_TooSmallSortIndex: A sortindex longer than 11 bytes should cause an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':'-1234567890123', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
            result = weave.get_item(storageServer, userID, self.password, 'coll', '1234')
            self.fail("Should have reported error with too-big SortIndex: got back %s" % result)
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error: was %s" % e)

    def testAdd_NegativeSortIndex(self):
        "testAdd_NegativeSortIndex: A negative sortindex is fine."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':'-5', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'ThisIsThePayload', 'modified':float(ts), 'sortindex':-5})

    def testAdd_FloatingPointSortIndex(self):
        "testAdd_FloatingPointSortIndex: A floating point sortindex will be rounded off."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':'5.5', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'ThisIsThePayload', 'modified':float(ts), 'sortindex':5})

    def testAdd_ClientCannotSetModified(self):
        "testAdd_ClientCannotSetModified: An attempt by the client to set the modified field is ignored."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'modified':'123456789', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        # server should impose its own modified stamp
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessAlmostEqual(float(ts), float(result['modified']))

    def skip_testAdd_MissingPayload(self):
        "testAdd_MissingPayload: An attempt to put a new item without a payload should report an error."

        # TODO: Skipping this test.  The current MySQL-based implementation
        # does not have an efficient way to provide this behavior.

        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'doesNotExist', 'parentid':'1234'}, withHost=test_config.HOST_NAME)
            try:
                result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
                self.fail("Should have had an error on attempt to modify metadata of non-existent object: got %s" % str(result))
            except weave.WeaveException, e:
                self.fail("Should have had an error on attempt to modify metadata of non-existent object: the object was not created, but no error resulted")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400 Bad Request") > 0, "Should have been an HTTP 400 error")

    def testAdd_MalformedJSON(self):
        "testAdd_MalformedJSON: An attempt to put an item with malformed JSON should report an error."
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', """{'id':'abcd1234', 'payload':'ThisIsThePayload}""", withHost=test_config.HOST_NAME)
            self.fail("Should have had an error on attempt to modify metadata of non-existent object")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("400") > 0, "Should have been an HTTP 400 error")

    def testModify(self):
        "testModify: An object can be modified by putting to the collection"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'aDifferentPayload'}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'aDifferentPayload', 'modified':float(ts2)})

    def testModify_IDFromURL(self):
        "testModify_IDFromURL: An object can be modified by directly accessing its URL"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':3, 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'sortindex':2, 'payload':'aDifferentPayload'}, urlID='1234', withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'aDifferentPayload', 'modified':float(ts2), 'sortindex':2})

    def testModify_sortIndex(self):
        "testModify_sortIndex: An object's sortIndex can be changed and does NOT update the modified date"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':3, 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':2}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'aPayload', 'modified':float(ts), 'sortindex':2})

    def testModify_parentID(self):
        "testModify_parentID: An object's parentID can be changed, and DOES update the modified date"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'parentid':3, 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'parentid':2}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'aPayload', 'modified':float(ts2), 'parentid':'2'})

    def testModify_predecessorID(self):
        "testModify_predecessorID: An object's predecessorID can be changed, and does NOT update the modified date"
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'predecessorid':'3', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'predecessorid':'2'}, withHost=test_config.HOST_NAME)
        #self.failUnlessEqual(ts, ts2)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'aPayload', 'modified':float(ts), 'predecessorid':'2'})
        # TODO: Changing the parentid changes the modification date, but changing the predecessorID does not.  Why?

    def testModify_ifModified_Modified(self):
        "testModify_ifModified_Modified: If an IfUnmodifiedSince header is provided, and the collection has changed, a modification attempt fails."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':3, 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        time.sleep(.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'newPayload'}, withHost=test_config.HOST_NAME)
        try:
            ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'sortindex':1},
                    ifUnmodifiedSince=round_time(ts), withHost=test_config.HOST_NAME)
            result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
            self.fail("Attempt to modify an item when the collection had changed after the ifUnmodifiedSince time should have failed: got %s" % str(result))
        except weave.WeaveException, e:
            self.failUnless(str(e).find("412 Precondition Failed") > 0, "Should have been an HTTP 412 error")

    def testAddMultiple(self):
        "testAddMultiple: A multiple add with some successes and some failures returns expected output."
        userID, storageServer = self.createCaseUser()
        objects = [
            {'id':'1', 'payload':'ThisIsThePayload'}, # all good
            {'id':'2'}, # missing payload
            {'id':'3', 'parentid':'a', 'predecessorid':'b', 'sortindex':3, 'payload':'A'}, # all good
            {'id':'4', 'parentid':''.join(['A' for i in range(70)]), 'payload':'A'}, # parent ID too long
            {'id':'5', 'predecessorid':''.join(['A' for i in range(70)]), 'payload':'A'}, # predecessor ID too long
            {'id':'6', 'sortindex':'blah', 'payload':'A'}, # sort index not integer
            {'payload':'payload'}, # missing ID
            {'id':'modifyme', 'sortindex':5, 'parentid':'a', 'predecessorid': 'b' }, # this will do a modify that changes the mod date
            {'id':'modifyme2', 'sortindex':5 }] # this will do a modify that does not change the mod date

        # Create the modify targets first
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'modifyme', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'modifyme2', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)

        multiresult = weave.add_or_modify_items(storageServer, userID, self.password, 'coll', objects, withHost=test_config.HOST_NAME)

        # can't really check the value of modified, but it's supposed to be there
#       self.failUnless("modified" in multiresult, "Result from a multi-object POST should contain a modified field.  Was: %s" % multiresult)
        self.failUnlessEqual(
            ["1", "2", "3", "modifyme", "modifyme2"], multiresult["success"])
        # TODO '2' fails silently right now; this is covered by a single test elsewhere
        self.failUnlessEqual(
            {'': ['invalid id'], "4": ['invalid parentid'], "5": ['invalid predecessorid'], "6": ['invalid sortindex']}, multiresult["failed"])

    def testAddMultiple_IfUnmodifiedSince_NotModified(self):
        "testAddMultiple_IfUnmodifiedSince_NotModified: If an IfUnmodifiedSince header is provided, and the collection has not changed, an attempt succeeds."
        userID, storageServer = self.createCaseUser()
        result = weave.add_or_modify_items(storageServer, userID, self.password, 'coll', [{'id':'1234', 'payload':'ThisIsThePayload'}], withHost=test_config.HOST_NAME)
        ts = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)['modified']         # TODO should use header
        weave.add_or_modify_items(storageServer, userID, self.password, 'coll',
                [{'id':'1234', 'payload':'ThisIsThePayload2'}],
                ifUnmodifiedSince=round_time(ts),
                withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(result['payload'], 'ThisIsThePayload2')

    def testAddMultiple_IfUnmodifiedSince_Modified(self):
        "testAddMultiple_IfUnmodifiedSince_Modified: If an IfUnmodifiedSince header is provided, and the collection has changed, the attempt fails."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'ThisIsThePayload2'}, withHost=test_config.HOST_NAME)
        try:
            ts3 = weave.add_or_modify_items(storageServer, userID, self.password, 'coll',
                    {'id':'1234', 'payload':'ThisIsThePayload'},
                     ifUnmodifiedSince=round_time(ts),
                      withHost=test_config.HOST_NAME)
            self.fail("Attempt to add an item when the collection had changed after the ifUnmodifiedSince time should have failed")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("412") > 0, "Should have been an HTTP 412 error")


    def testQuota(self):
        "testQuota: Storing an item should increase the quota usage for the user"
        userID, storageServer = self.createCaseUser()
        used, total = weave.get_quota(storageServer, userID, self.password, withHost=test_config.HOST_NAME)
        self.failUnlessEqual(used, 0)

        for i in range(10):
            wbo =  {'id': '1234'+str(i), 'sortindex': 3, 'payload': 'a' * 500}

            ts = weave.add_or_modify_item(storageServer, userID, self.password,
                                          'coll', wbo, withHost=test_config.HOST_NAME)

        used2, total2 = weave.get_quota(storageServer, userID, self.password, withHost=test_config.HOST_NAME)
        self.assertEquals(total, total2)
        self.assertTrue(used2 > used)
        self.assertTrue(used2 > 4)

        # And we also need to test add (and modify) multiple

    def testCollection_SameIDs(self):
        "testCollection_SameIDs: Two objects with the same IDs can exist in different collections."
        userID, storageServer = self.createCaseUser()
        weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        weave.add_or_modify_item(storageServer, userID, self.password, 'coll2', {'id':'1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
        weave.get_item(storageServer, userID, self.password, 'coll2', '1234', withHost=test_config.HOST_NAME)

    def testCollectionCounts(self):
        "testCollectionCounts: The count of objects should be updated correctly."
        userID, storageServer = self.createCaseUser()

        wbo = {'id': '1', 'payload': 'aPayload'}
        for collection in ('coll', 'coll2', 'coll3', 'coll4'):

            weave.add_or_modify_item(storageServer, userID,
                                     self.password, collection, wbo,
                                     withHost=test_config.HOST_NAME)

        wbo2 = {'id': '2', 'payload': 'aPayload'}
        weave.add_or_modify_item(storageServer, userID,
                                 self.password, 'coll4', wbo2,
                                 withHost=test_config.HOST_NAME)

        counts = weave.get_collection_counts(storageServer, userID,
                                             self.password,
                                             withHost=test_config.HOST_NAME)

        counts = [(k, int(v)) for k, v in counts.items()]
        counts.sort()
        self.failUnlessEqual(counts, [("coll", 1), ("coll2", 1),
                                      ("coll3", 1), ("coll4", 2)])

    def testCollectionTimestamps(self):
        "testCollectionTimestamps: The timestamps of objects should be returned correctly."
        userID, storageServer = self.createCaseUser()
        ts = {}
        wbo1 = {'id':'1', 'payload':'aPayload'}
        wbo2 = {'id':'2', 'payload':'aPayload'}

        ts['coll'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll', wbo1, withHost=test_config.HOST_NAME)
        ts['coll2'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll2', wbo1, withHost=test_config.HOST_NAME)
        ts['coll3'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll3', wbo1, withHost=test_config.HOST_NAME)
        ts['coll4'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll4', wbo1, withHost=test_config.HOST_NAME)
        ts['coll3'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll3', wbo1, withHost=test_config.HOST_NAME)
        ts['coll4'] = weave.add_or_modify_item(storageServer, userID,
                self.password, 'coll4', wbo2, withHost=test_config.HOST_NAME)
        result = weave.get_collection_timestamps(storageServer, userID,
                self.password, withHost=test_config.HOST_NAME)

        for col, value in ts.items():
            self.failUnlessAlmostEqual(Decimal(value), result[col])

    def testCollectionIDs(self):
        "testCollectionIDs: The IDs should be returned correctly."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'2', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'3', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
        counts = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        counts.sort()
        self.failUnlessEqual(counts, ["1","2","3"])


    def testGet_multiple(self):
        "testGet_multiple: Attempt to get multiple objects with 'full'"
        userID, storageServer = self.createCaseUser()
        result = weave.add_or_modify_items(storageServer, userID, self.password, 'coll', [{'id':"id%s" % i, 'payload':'aPayload', 'sortindex': i} for i in range(1,3)], withHost=test_config.HOST_NAME)
        # TODO use the timestamp in the header for the assertion
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="full=1", withHost=test_config.HOST_NAME)

        lines = []
        for line in result:
            line = line.items()
            line.sort()
            lines.append(line)

        lines.sort()

        ts = Decimal(result[0]['modified'])
        expected = [[('id', 'id2'), ('modified', ts), ('payload', 'aPayload'),
                     ('sortindex', 2)],
                    [('id', 'id1'), ('modified', ts), ('payload', 'aPayload'),
                     (u'sortindex', 1)]]
        expected.sort()

        self.failUnlessEqual(lines, expected)

    def testGet_NoObject(self):
        "testGet_NoObject: Attempt to get a non-existent object should return 404."
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.get_item(storageServer, userID, self.password, 'coll', 'noSuchObject', withHost=test_config.HOST_NAME)
            self.fail("Should have failed to get a non-existen object")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("404") > 0, "Should have been an HTTP 404 error, was %s" % str(e))

    def testGet_NoAuth(self):
        "testGet_NoAuth: Attempt to get an object with no authorization should return a 401"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'abcd1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
            ts = weave.get_item(storageServer, userID, None, 'coll', 'abcd1234', withAuth=False, withHost=test_config.HOST_NAME)
            self.fail("Should have raised an error for no authorization")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("401 Unauthorized") > 0, "Should have been an HTTP 401 error, was %s" % str(e))

    def testGet_BadPassword(self):
        "testGet_BadPassword: Attempt to get an object with wrong password should return an error"
        userID, storageServer = self.createCaseUser()
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'abcd1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
            ts = weave.get_item(storageServer, userID, "wrongPassword", 'coll', 'abcd1234', withHost=test_config.HOST_NAME)
            self.fail("Should have raised an error for bad password")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("401 Unauthorized") > 0, "Should have been an HTTP 401 error, was %s" % str(e))

    def testGet_UserPathMismatch(self):
        "testGet_UserPathMismatch: Attempt to get an object with wrong user account should return an error"
        if test_config.USERNAME:
            # We do not currently support this test with specified usernames
            return

        userID, storageServer = self.createCaseUser()
        userID2, storageServer2 = self.createCaseUser(forceNewUser=True)
        try:
            ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'abcd1234', 'payload':'aPayload'}, withHost=test_config.HOST_NAME)
            ts = weave.get_item(storageServer, userID, self.password, 'coll', 'abcd1234', withAuthUser=userID2, withHost=test_config.HOST_NAME)
            self.fail("Should have raised an error for cross-user access")
        except weave.WeaveException, e:
            # WEAVE_ERROR_USERID_PATH_MISMATCH
            self.failUnless(str(e).find("401") > 0, "Should have been an HTTP 401 error, was %s" % str(e))

    def helper_testGet(self):
        'Helper function to set up many of the testGet functions'
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '3'}, withHost=test_config.HOST_NAME)
        time.sleep(.2)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'2', 'payload':'aPayload', 'parentid':'def', 'predecessorid': 'def', 'sortindex': '5'}, withHost=test_config.HOST_NAME)
        time.sleep(.2)
        ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'3', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '1'}, withHost=test_config.HOST_NAME)
        return (userID, storageServer, [ts, ts2, ts3])

    def testGet_ByParentID(self):
        "testGet_ByParentID: Attempt to get objects with a ParentID filter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="parentid=ABC", withHost=test_config.HOST_NAME)
        result.sort()
        self.failUnlessEqual(['1', '3'], result)

    def testGet_ByPredecessorID(self):
        "testGet_ByPredecessorID: Attempt to get objects with a PredecessorID filter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="predecessorid=abc", withHost=test_config.HOST_NAME)
        result.sort()
        self.failUnlessEqual(['1', '3'], result)

    def testGet_ByNewer(self):
        "testGet_ByNewer: Attempt to get objects with a Newer filter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll',
                                          params="newer=%s" % round_time(ts[0]),
                                          withHost=test_config.HOST_NAME)
        result.sort()
        self.failUnlessEqual(['2', '3'], result)

    def testGet_ByOlder(self):
        "testGet_ByOlder: Attempt to get objects with a Older filter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll',
                                          params="older=%s" % round_time(ts[2],
                                              -.01),
                                          withHost=test_config.HOST_NAME)
        result.sort()
        self.failUnlessEqual(['1', '2'], result)

    def testGet_Sort_Oldest(self):
        "testGet_Sort_Oldest: Attempt to get objects with a sort 'oldest' parameter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=oldest", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['1', '2', '3'], result)

    def testGet_Sort_Newest(self):
        "testGet_Sort_Newest: Attempt to get objects with a sort 'newest' parameter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=newest", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3', '2', '1'], result)

    def testGet_Sort_Index(self):
        "testGet_Sort_Index: Attempt to get objects with a sort 'index' parameter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2', '1', '3'], result)

    def testGet_Limit(self):
        "testGet_Limit: Attempt to get objects with a 'limit' parameter works"
        userID, storageServer, ts = self.helper_testGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index&limit=2", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2', '1'], result)

    def testGet_Limit_Negative(self):
        "testGet_Limit_Negative: Attempt to get objects with a negative 'limit' should ignore the limit"
        userID, storageServer = self.createCaseUser()
        weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1', 'payload':'aPayload', 'sortindex': 5}, withHost=test_config.HOST_NAME)
        weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'2', 'payload':'aPayload', 'sortindex': 6}, withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index&limit=-5", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2', '1'], result)

    def testGet_Offset(self):
        "testGet_Offset: Attempt to get objects with an 'offset' parameter works"
        userID, storageServer = self.createCaseUser()
        [weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':i, 'payload':'aPayload', 'sortindex': i}, withHost=test_config.HOST_NAME) for i in range(1,5)]
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index&limit=2&offset=2", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2', '1'], result) # should be 4,3,2,1; skip 2, limit 2

    def testGet_Offset_OffRange(self):
        "testGet_Offset: Attempt to get objects with an 'offset' higher than the highest value should return an empty set"
        userID, storageServer = self.createCaseUser()
        [weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':i, 'payload':'aPayload', 'sortindex': i}, withHost=test_config.HOST_NAME) for i in range(1,5)]
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index&limit=2&offset=5", withHost=test_config.HOST_NAME)
        self.failUnlessEqual([], result)

    def testGet_Offset_Negative(self):
        "testGet_Offset_Negative: Attempt to get objects with a negative 'offset' ignore the offset"
        userID, storageServer = self.createCaseUser()
        weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1', 'payload':'aPayload', 'sortindex': 5}, withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', params="sort=index&limit=2&offset=-5", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['1'], result)

    def testGet_whoisi(self):
        "testGet_whoisi: Attempt to get multiple objects, specifying whoisi output format, without 'full'."
        userID, storageServer = self.createCaseUser()
        [weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':"id%s" % i, 'payload':'aPayload', 'sortindex': i}, withHost=test_config.HOST_NAME) for i in range(1,3)]
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', asJSON=False, outputFormat="application/whoisi", withHost=test_config.HOST_NAME)
        self.failUnlessEqual("\x00\x00\x00\x05\"id1\"\x00\x00\x00\x05\"id2\"", result)

    def testGet_whoisi_full(self):
        "testGet_whoisi_full: Attempt to get multiple objects, specifying whoisi output format, with 'full'"
        userID, storageServer = self.createCaseUser()
        ts = [weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':"id%s" % i, 'payload':'aPayload', 'sortindex': i}, withHost=test_config.HOST_NAME) for i in range(1,3)]
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', asJSON=False, params="full=1", outputFormat="application/whoisi", withHost=test_config.HOST_NAME)

        # The whoisi format starts with a hex-encoded length.
        # Since modified strings could be variable length depending on how many
        # fractional digits are present, we have to calculate.

        # Default python conversion does what we want here - "5", "5.1", or "5.11".
        expected1 = {"id": "id1", "modified": float(ts[0]), "sortindex": 1, "payload": "aPayload"}
        expected2 = {"id": "id2", "modified": float(ts[1]), "sortindex": 2, "payload": "aPayload"}
        expected1 = expected1.items()
        expected1.sort()
        expected2 = expected2.items()
        expected2.sort()
        expected = [expected1, expected2]

        lines = []
        pos = 0
        while pos < len(result):
            # getting the 32bits value
            size = result[pos:pos + 4]
            size = struct.unpack('!I', size)[0]

            # extracting the line
            line = result[pos + 4:pos + size + 4]
            line = json.loads(line)
            id_ = line['id']
            items = line.items()
            items.sort()
            lines.append((id_, items))
            pos = pos + size + 4

        lines.sort()
        lines = [line for id_, line in lines]
        self.failUnlessEqual(lines, expected)

        #'\x00\x00\x00H{"id":"id1","modified":'+ts[0]+',"sortindex":1,"payload":"aPayload"}\x00\x00\x00H{"id":"id2","modified":'+ts[1]+',"sortindex":2,"payload":"aPayload"}',  result)

    def testGet_newLines(self):
        "testGet_newLines: Attempt to get multiple objects, specifying newlines output format, without 'full'"
        userID, storageServer = self.createCaseUser()
        ts = [weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':"id%s" % i, 'payload':'aPayload', 'sortindex': i}, withHost=test_config.HOST_NAME) for i in range(1,3)]
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', asJSON=False, params="full=1", outputFormat="application/newlines", withHost=test_config.HOST_NAME)

        lines = []
        for line in result.split('\n'):
            line = line.strip()
            if line == '':
                continue
            line = json.loads(line).items()
            line.sort()
            lines.append(line)

        lines.sort()
        expected = [[('id', 'id2'), ('modified', float(ts[1])),
                     ('payload', u'aPayload'), ('sortindex', 2)],
                    [('id', 'id1'), ('modified', float(ts[0])),
                     ('payload', 'aPayload'), ('sortindex', 1)]]

        expected.sort()
        self.failUnlessEqual(lines, expected)


    def helper_testDelete(self):
        'Helper function to set up many of the testDelete functions'
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '3'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'2', 'payload':'aPayload', 'parentid':'def', 'predecessorid': 'def', 'sortindex': '5'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'3', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '1'}, withHost=test_config.HOST_NAME)
        return (userID, storageServer, [ts, ts2, ts3])

    def testDelete(self):
        "testDelete: Attempt to delete objects by ID should work"
        userID, storageServer, ts = self.helper_testDelete()
        ts = weave.delete_item(storageServer, userID, self.password, 'coll', '1', withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)

        # Should be ['2', '3'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('2' in result)
        self.failUnless('3' in result)

        try:
            ts2 = weave.get_item(storageServer, userID, self.password, 'coll', '1', withHost=test_config.HOST_NAME)
            self.fail("Should have raised a 404 exception on attempt to access deleted object")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("404 Not Found") > 0, "Should have been an HTTP 404 error")

        # Delete always updates the timestamp: even if nothing changes
        # TODO This fails if memcache isn't turned on; the timestamp rolls backwards
        timestamps = weave.get_collection_timestamps(storageServer, userID, self.password, withHost=test_config.HOST_NAME)
        if test_config.memcache:
            self.failUnlessEqual({'coll':float(ts)}, timestamps)
        # TODO: Provide negative case logic for memcache

    def testDelete_NoMatch(self):
        "testDelete_NoMatch: Attempt to delete a missing object should not cause an error, and updates the timestamp"
        userID, storageServer, ts = self.helper_testDelete()
        ts = weave.delete_item(storageServer, userID, self.password, 'coll', '4', withHost=test_config.HOST_NAME)
        timestamps = weave.get_collection_timestamps(storageServer, userID, self.password, withHost=test_config.HOST_NAME)
        if test_config.memcache:
            self.failUnlessEqual({'coll':float(ts)}, timestamps)
        # TODO This fails if memcache isn't turned on

    def testDelete_ByParentID(self):
        "testDelete_ByParentID: Attempt to delete objects with a ParentID filter works"
        userID, storageServer, ts = self.helper_testDelete()
        ts = weave.delete_items(storageServer, userID, self.password, 'coll', params="parentid=ABC", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2'], result)

    def testDelete_ByPredecessorID(self):
        "testDelete_ByPredecessorID: Attempt to delete objects with a PredecessorID filter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="predecessorid=abc", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2'], result)

    def testDelete_ByNewer(self):
        "testDelete_ByNewer: Attempt to delete objects with a Newer filter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll',
                params="newer=%s" % round_time(ts[0]), withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['1'], result)

    def testDelete_ByOlder(self):
        "testDelete_ByOlder: Attempt to delete objects with a Older filter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll',
                params="older=%s" % round_time(ts[2], -.01), withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3'], result)

    def testDelete_Sort_Oldest(self):
        "testDelete_Sort_Oldest: Attempt to delete objects with a sort 'oldest' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="sort=oldest&limit=2", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3'], result)

    def testDelete_Sort_Newest(self):
        "testDelete_Sort_Newest: Attempt to delete objects with a sort 'newest' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="sort=newest&limit=2", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['1'], result)

    def testDelete_Sort_Index(self):
        "testDelete_Sort_Index: Attempt to delete objects with a sort 'index' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="sort=index&limit=2", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3'], result)

    def testDelete_Limit(self):
        "testDelete_Limit: Attempt to delete objects with a 'limit' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="sort=oldest&limit=1", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)

        # Should be ['2', '3'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('2' in result)
        self.failUnless('3' in result)

    def skip_testDelete_LimitOffset(self):
        "testDelete_LimitOffset: Attempt to delete objects with a 'limit' and 'offset' parameter works"

        # TODO: The server does not currently support delete by limit with an offset.

        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="sort=index&limit=1&offset=1", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)

        # Should be ['1', '3'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('1' in result)
        self.failUnless('3' in result)

        self.failUnlessEqual(['1', '3'], result)

    def testDelete_indexAbove(self):
        "testDelete_indexAbove: Attempt to delete objects with an 'index_above' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="index_above=2", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3'], result, "Items with an index above 2 should have been deleted")
        # BUG wrong variable in params

    def testDelete_indexBelow(self):
        "testDelete_indexBelow: Attempt to delete objects with an 'index_below' parameter works"
        userID, storageServer, ts = self.helper_testDelete()
        result = weave.delete_items(storageServer, userID, self.password, 'coll', params="index_below=4", withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'coll', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2'], result, "Items with an index below 4 should have been deleted")
        # BUG wrong variable in params

    def testDelete_IfUnmodifiedSince_NotModified(self):
        "testDelete_IfUnmodifiedSince_NotModified: If an IfUnmodifiedSince header is provided, and the collection has not changed, the attempt succeeds."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'coll', {'id':'1234', 'payload':'ThisIsThePayload2'}, withHost=test_config.HOST_NAME)
        result = weave.delete_item(storageServer, userID, self.password, 'coll', '1234',
                ifUnmodifiedSince=round_time(ts2), withHost=test_config.HOST_NAME)
        try:
            weave.get_item(storageServer, userID, self.password, 'coll', '1234', withHost=test_config.HOST_NAME)
            self.fail("Should have raised a 404 exception on attempt to access deleted object")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("404 Not Found") > 0, "Should have been an HTTP 404 error")



    def testDelete_IfUnmodifiedSince_Modified(self):
        "testDelete_IfUnmodifiedSince_Modified: If an IfUnmodifiedSince header is provided, and the collection has changed, the attempt fails."
        userID, storageServer = self.createCaseUser()
        oid = randid()

        ts = weave.add_or_modify_item(storageServer, userID, self.password,
                                      'coll', {'id': oid,
                                               'payload':'ThisIsThePayload'},
                                      withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password,
                                       'coll', {'id': oid,
                                                'payload':'ThisIsThePayload2'},
                                       withHost=test_config.HOST_NAME)
        try:
            result = weave.delete_item(storageServer, userID, self.password,
                                       'coll', oid, ifUnmodifiedSince=round_time(ts),
                                       withHost=test_config.HOST_NAME)
            self.fail("Attempt to delete an item that hasn't modified, with an ifModifiedSince header, should have failed")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("412 Precondition Failed") > 0, "Should have been an HTTP 412 error")


    def testAddTab(self):
        "testAddTab: A tab object can be created with all relevant parameters, and everything persists correctly."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'abcd1234', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        result = weave.get_item(storageServer, userID, self.password, 'tabs', 'abcd1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'abcd1234', 'payload':'ThisIsThePayload', 'modified':float(ts)})

    def testAddTab_IfUnmodifiedSince_NotModified(self):
        "testAddTab_IfUnmodifiedSince_NotModified: If an IfUnmodifiedSince header is provided, and the collection has not been changed, an attempt succeeds."
        userID, storageServer = self.createCaseUser()

        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'1234', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        time.sleep(0.2)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs',
                {'id':'1234', 'payload':'ThisIsThePayload'},
                ifUnmodifiedSince=round_time(ts), withHost=test_config.HOST_NAME)

        result = weave.get_item(storageServer, userID, self.password, 'tabs', '1234', withHost=test_config.HOST_NAME)
        self.failUnlessObjsEqualWithDrift(result, {'id':'1234', 'payload':'ThisIsThePayload', 'modified':float(ts2)})

    def testAddTab_IfUnmodifiedSince_Modified(self):
        "testAddTab_IfUnmodifiedSince_Modified: If an IfUnmodifiedSince header is provided, and the collection has changed, the attempt fails."
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'1234', 'payload':'ThisIsThePayload'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'1234', 'payload':'ThisIsThePayload2'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        try:
            ts3 = weave.add_or_modify_item(storageServer, userID, self.password,
                    'tabs', {'id':'1234', 'payload':'ThisIsThePayload'},
                    ifUnmodifiedSince=round_time(ts), withHost=test_config.HOST_NAME)
            self.fail("Attempt to add an item when the collection had changed after the ifModifiedSince time should have failed")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("412 Precondition Failed") > 0, "Should have been an HTTP 412 error")

    def testGetTab_ByNewer(self):
        "testGetTab_ByNewer: Attempt to get tabs with a Newer filter works"
        userID, storageServer, ts = self.helper_tabTestGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'tabs',
                params="newer=%s" % round_time(ts[0]), withHost=test_config.HOST_NAME)

        # Should be ['2', '3'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('2' in result)
        self.failUnless('3' in result)

    def testGetTab_ByOlder(self):
        "testGetTab_ByOlder: Attempt to get tabs with a Older filter works"
        userID, storageServer, ts = self.helper_tabTestGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'tabs',
                params="older=%s" % round_time(ts[2], -.01), withHost=test_config.HOST_NAME)
        # Should be ['1', '2'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('1' in result)
        self.failUnless('2' in result)

    def testGetTab_ByIds(self):
        "testGetTab_ByIds: Attempt to get tabs from a set of ids"
        userID, storageServer, ts = self.helper_tabTestGet()
        result = weave.get_collection_ids(storageServer, userID, self.password, 'tabs', params="ids=1,2,4", withHost=test_config.HOST_NAME)

        # Should be ['1', '2'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('1' in result)
        self.failUnless('2' in result)

    def helper_tabTestGet(self):
        'Helper function to set up many of the testGet functions'
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'1', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '3'}, withHost=test_config.HOST_NAME)
        time.sleep(.02)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'2', 'payload':'aPayload', 'parentid':'def', 'predecessorid': 'def', 'sortindex': '5'}, withHost=test_config.HOST_NAME)
        time.sleep(.02)
        ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs', {'id':'3', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '1'}, withHost=test_config.HOST_NAME)
        return (userID, storageServer, [ts, ts2, ts3])

    def testDeleteTab(self):
        "testDeleteTab: Attempt to delete tabs by ID should work"
        userID, storageServer, ts = self.helper_testDeleteTab()
        ts = weave.delete_item(storageServer, userID, self.password,
                'tabs', '1', withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID,
                self.password, 'tabs', withHost=test_config.HOST_NAME)

        # Should be ['2', '3'] in any order
        self.failUnlessEqual(2, len(result))
        self.failUnless('2' in result)
        self.failUnless('3' in result)

        try:
            ts2 = weave.get_item(storageServer, userID, self.password, 'tabs', '1', withHost=test_config.HOST_NAME)
            self.fail("Should have raised a 404 exception on attempt to access deleted object")
        except weave.WeaveException, e:
            self.failUnless(str(e).find("404 Not Found") > 0, "Should have been an HTTP 404 error")

        # Delete always updates the timestamp: even if nothing changes
        # TODO This fails if memcache isn't turned on; the timestamp rolls backwards
        timestamps = weave.get_collection_timestamps(storageServer, userID, self.password, withHost=test_config.HOST_NAME)
        if test_config.memcache:
            self.failUnlessEqual({'tabs':float(ts)}, timestamps)

    def testDeleteTab_ByNewer(self):
        "testDeleteTab_ByNewer: Attempt to delete tabs with a Newer filter works"
        userID, storageServer, ts = self.helper_testDeleteTab()
        result = weave.delete_items(storageServer, userID, self.password,
                'tabs', params="newer=%s" % round_time(ts[0]), withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'tabs', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['1'], result)

    def testDeleteTab_ByOlder(self):
        "testDeleteTab_ByOlder: Attempt to delete tabs with a Older filter works"
        userID, storageServer, ts = self.helper_testDeleteTab()
        result = weave.delete_items(storageServer, userID, self.password,
                'tabs', params="older=%s" % round_time(ts[2], -.01), withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(storageServer, userID, self.password, 'tabs', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['3'], result)

    def helper_testDeleteTab(self):
        'Helper function to set up many of the testDelete functions'
        userID, storageServer = self.createCaseUser()
        ts = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs',
                {'id':'1', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '3'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts2 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs',
                {'id':'2', 'payload':'aPayload', 'parentid':'def', 'predecessorid': 'def', 'sortindex': '5'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        ts3 = weave.add_or_modify_item(storageServer, userID, self.password, 'tabs',
                {'id':'3', 'payload':'aPayload', 'parentid':'ABC', 'predecessorid': 'abc', 'sortindex': '1'}, withHost=test_config.HOST_NAME)
        time.sleep(0.1)
        return (userID, storageServer, [ts, ts2, ts3])



# TODO: Test X-Weave-Timestamp header




# Doc bugs:
# predecessorID is not documented in DELETE
# indexAbove and indexBelow are not documented in DELETE
# Behavior of offset when limit is missing is not defined

class TestStorageLarge(unittest.TestCase):

    def setUp(self):
        self.userList = []
        self.email = 'testuser@test.com'

        if test_config.USERNAME:
            # Specified username: hard-code it, and clear out any old records

            if not test_config.PASSWORD:
                raise ValueError("If username is provided, a password must also be provided")
            self.userID = test_config.USERNAME
            self.password = test_config.PASSWORD
            storageServer = weave.getUserStorageNode(test_config.SERVER_BASE,
                                                     self.userID, self.password,
                                                     withHost=test_config.HOST_NAME)
            self.storageServer = storageServer.rstrip('/')
            #if test_config.STORAGE_SCHEME and test_config.STORAGE_SERVER:
            #    self.storageServer = "%s://%s" % (test_config.STORAGE_SCHEME, test_config.STORAGE_SERVER)
            weave.delete_all(self.storageServer, self.userID, self.password, withHost=test_config.HOST_NAME)

        else:

            self.email = 'testuser@test.com'
            self.password = 'mypassword'
            while True:
                self.userID = 'weaveunittest_' + ''.join([chr(random.randint(ord('a'), ord('z'))) for i in xrange(10)])
                if not weave.checkNameAvailable(test_config.SERVER_BASE, self.userID, withHost=test_config.HOST_NAME):
                    print "%s not available" % self.userID
                    continue
                weave.createUser(test_config.SERVER_BASE, self.userID, self.password,
                                 self.email, withHost=test_config.HOST_NAME,
                                 secret=test_config.SECRET)
                break
            self.failIf(weave.checkNameAvailable(test_config.SERVER_BASE, self.userID, withHost=test_config.HOST_NAME))
            storageServer = weave.getUserStorageNode(test_config.SERVER_BASE, self.userID, self.password, withHost=test_config.HOST_NAME)
            self.storageServer = storageServer.rstrip('/')

    def testStorage(self):
        item1 = '{"id": 1, "sortindex": 1, "payload": "123456789abcdef"}'
        item2 = '{"id": 2, "sortindex": 2, "payload":"abcdef123456789"}'
        item3 = '{"id": 3, "parentid": 1, "sortindex": 3, "payload":"123abcdef123456789"}'
        item4 = '{"id": 4, "parentid": 1, "sortindex": 4, "payload":"567abcdef123456789"}'
        item5 = '{"parentid": 1, "sortindex": 4, "payload":"567abcdef123456789"}'
        item4_update = '{"id": 4, "parentid": 1, "sortindex": 5}'

        TEST_WEAVE_QUOTA = True
        timestamp1 = weave.add_or_modify_item(self.storageServer, self.userID,
                self.password, 'history', item1, withHost=test_config.HOST_NAME)
        self.failUnless(abs(time.time() - float(timestamp1)) < 10,
                "Timestamp drift between client and server must be <10 sec") # no more than 10 seconds of drift

        #if TEST_WEAVE_QUOTA:
        #   quota = weave.get_quota(test_config.SERVER_BASE, self.userID, self.password)
        timestamp2 = weave.add_or_modify_item(self.storageServer, self.userID,
                self.password, 'foo', item2, withHost=test_config.HOST_NAME)

        counts = weave.get_collection_counts(self.storageServer, self.userID,
                self.password, withHost=test_config.HOST_NAME)
        self.assertEqual(len(counts), 2)
        self.assertEqual(int(counts['history']), 1)
        self.assertEqual(int(counts['foo']), 1)

        timestamps = weave.get_collection_timestamps(self.storageServer, self.userID,
                                                     self.password,
                                                     withHost=test_config.HOST_NAME)
        self.assertEqual(timestamps['foo'], Decimal(timestamp2))
        self.assertEqual(timestamps['history'], Decimal(timestamp1))

        result = weave.get_item(self.storageServer, self.userID, self.password,
                'foo', '2', withHost=test_config.HOST_NAME)
        self.failUnlessEqual(result['id'], '2')
        self.failUnlessEqual(result['sortindex'], 2)
        self.failUnlessEqual(result['payload'], "abcdef123456789")
        self.failUnlessAlmostEqual(result['modified'], Decimal(timestamp2))
        result = weave.get_collection_ids(self.storageServer, self.userID,
                                          self.password, 'foo',
                                          withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['2'], result)

        try:
            result = weave.add_or_modify_item(self.storageServer, self.userID, self.password, 'foo', item1,
                    ifUnmodifiedSince=Decimal(timestamp1), withHost=test_config.HOST_NAME)
            self.fail("Should have failed on too-old timestamp")
        except weave.WeaveException, e:
            pass

        result = weave.add_or_modify_items(self.storageServer, self.userID, self.password, 'foo',
            "[%s,%s,%s]" % (item3, item4, item5), withHost=test_config.HOST_NAME)


        # xxxwhy this is not returning the 'modified' timestamp ? Tarek
        successes = [int(s) for s in result['success']]
        successes.sort()
        self.failUnlessEqual(successes, [3, 4])


        result = weave.get_collection_ids(self.storageServer, self.userID, self.password, 'foo', "sort=index", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['4', '3', '2'], result)

        result = weave.get_collection_ids(self.storageServer, self.userID, self.password, 'foo', "sort=index&parentid=1", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['4', '3'], result)

        timestamp3 = weave.delete_item(self.storageServer, self.userID, self.password, 'foo', '3', withHost=test_config.HOST_NAME)
        result = weave.get_collection_ids(self.storageServer, self.userID, self.password, 'foo', "sort=index", withHost=test_config.HOST_NAME)
        self.failUnlessEqual(['4', '2'], result, "ID 3 should have been deleted")

        counts = weave.get_collection_counts(self.storageServer, self.userID, self.password, withHost=test_config.HOST_NAME)
        counts = [(k, int(v)) for k, v in counts.items()]
        counts.sort()
        self.failUnlessEqual([('foo', 2), ('history', 1)], counts)

        timestamp4 = weave.add_or_modify_item(self.storageServer, self.userID, self.password,
                'foo', item4_update, withHost=test_config.HOST_NAME) # bump sortindex up; parentid is also updated
        result = weave.get_item(self.storageServer, self.userID, self.password, 'foo',
                '4', withHost=test_config.HOST_NAME)
        self.failUnlessAlmostEqual(result['modified'], Decimal(timestamp4))
        del result['modified']
        self.failUnlessEqual({'id':'4', 'parentid':'1', 'sortindex': 5,
                            'payload':'567abcdef123456789'}, result)

        # delete updates the timestamp, all items in "foo" should be gone but
        # one
        timestamp5 = weave.delete_items_older_than(self.storageServer, self.userID, self.password, 'foo',
                                                   float(timestamp4), withHost=test_config.HOST_NAME)
        counts = weave.get_collection_counts(self.storageServer, self.userID,
                self.password, withHost=test_config.HOST_NAME)
        counts = [(k, int(v)) for k, v in counts.items()]
        counts.sort()
        self.failUnlessEqual([('foo', 1), ('history', 1)], counts)

        timestamps = weave.get_collection_timestamps(self.storageServer,
                self.userID, self.password, withHost=test_config.HOST_NAME)
        if test_config.memcache:
            self.failUnlessEqual({'history': Decimal(timestamp1),
                                  'foo': Decimal(timestamp5)}, timestamps)
        # TODO if memcache isn't on check for other behavior

        try:
            result = weave.delete_all(self.storageServer, self.userID,
                    self.password, confirm=False, withHost=test_config.HOST_NAME)
            self.fail("Should have received an error for delete without confirmatation header")
        except weave.WeaveException, e:
            pass

        timestamp = weave.delete_all(self.storageServer, self.userID, self.password, withHost=test_config.HOST_NAME)


    def testBadMethod(self):
        req = urllib2.Request("%s/1.0/%s" % (self.storageServer, self.userID))
        req.get_method = lambda: 'HEAD'
        try:
            f = opener.open(req)
            result = f.read()
            self.fail("Should have reported an error on a HEAD attempt")
        except urllib2.URLError, e:
            pass

    def skiptestBadFunction(self):
        req = urllib2.Request("%s/1.0/%s/badfunction/" % (self.storageServer, self.userID))
        base64string = base64.encodestring('%s:%s' % (self.userID, self.password))[:-1]
        req.add_header("Authorization", "Basic %s" % base64string)
        f = opener.open(req)
        result = f.read()
        # this should be allowed and return an empty body
        self.failUnlessEqual("", result)
