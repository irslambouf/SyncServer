# -*- encoding: utf-8 -*-
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
import random

from services.util import BackendError, BackendTimeoutError
from sqlalchemy.exc import OperationalError

try:
    import ldap
    from services.ldappool import StateConnector
    from services.auth.ldapsql import LDAPAuth
    LDAP = True
except ImportError:
    LDAP = False

from services.util import validate_password, ssha


if LDAP:
    # memory ldap connector for the tests
    users = {
            'uidNumber=1,ou=users,dc=mozilla':

            {'uidNumber': ['1'],
                'userPassword': [ssha('bind')],
                'uid': ['testuser'],
                'account-enabled': ['Yes'],
                'mail': ['tarek@mozilla.com'],
                'cn': ['tarek'],
                'primaryNode': ['weave:'],
                'rescueNode': ['weave:'],
                },

            'uid=adminuser,ou=users,dc=mozilla':

            {'uidNumber': ['-1'],
                'userPassword': [ssha('admin')],
                'uid': ['adminuser'],
                'account-enabled': ['Yes'],
                'mail': ['tarek@mozilla.com'],
                'cn': ['tarek'],
                'primaryNode': ['weave:'],
                'rescueNode': ['weave:'],
                },

            'uid=binduser,ou=users,dc=mozilla':

            {'uidNumber': ['0'],
                'userPassword': [ssha('bind')],
                'uid': ['binduser'],
                'account-enabled': ['Yes'],
                'mail': ['tarek@mozilla.com'],
                'cn': ['tarek'],
                'primaryNode': ['weave:'],
                'rescueNode': ['weave:']
                },
            }

    class MemoryStateConnector(StateConnector):

        users = users

        def __init__(self, uri, bind=None, passwd=None, **kw):
            if bind is not None and passwd is not None:
                self.simple_bind_s(bind, passwd)
            self._uri = uri
            self._next_id = 30
            self._l = self
            self.connected = False
            self.who = ''

        def unbind_ext(self, *args, **kw):
            if random.randint(1, 10) == 1:
                raise ldap.LDAPError('Invalid State')
            self.connected = False
            self.who = ''

        def __repr__(self):
            return '<%s - %s>' % (self.who, self.cred)

        def simple_bind_s(self, who, passwd):
            if who not in self.users:
                raise ldap.NO_SUCH_OBJECT(who)

            user = self.users[who]
            pass_ = user['userPassword'][0]
            if not validate_password(passwd.decode('utf8'), pass_):
                raise ldap.INVALID_CREDENTIALS(who, passwd)

            self.connected = True
            self.who = who
            self.cred = passwd

        def search_st(self, dn, *args, **kw):
            if dn in self.users:
                return [(dn, self.users[dn])]
            elif dn in ('ou=users,dc=mozilla', 'dc=mozilla', 'md5'):
                key, field = kw['filterstr'][1:-1].split('=')
                for dn_, value in self.users.items():
                    if key not in value:
                        raise Exception(value)
                    if value[key][0] != field:
                        continue
                    return [(dn_, value)]
            raise ldap.NO_SUCH_OBJECT

        def add_s(self, dn, user):
            if dn in self.users:
                raise Exception('%r already exists' % dn)
            self.users[dn] = {}
            for key, value in user:
                if not isinstance(value, list):
                    value = [value]
                self.users[dn][key] = value

            if 'uidNumber' not in self.users[dn]:
                self.users[dn]['uidNumber'] = [self._next_id]
                self._next_id += 1
            return ldap.RES_ADD, ''

        def modify_s(self, dn, user):
            if dn in self.users:
                for type_, key, value in user:
                    if not isinstance(value, list):
                        value = [value]
                    self.users[dn][key] = value
            return ldap.RES_MODIFY, ''

        def delete_s(self, dn, **kw):
            if dn in self.users:
                del self.users[dn]
            elif dn in ('ou=users,dc=mozilla', 'md5'):
                key, field = kw['filterstr'][1:-1].split('=')
                for dn_, value in self.users.items():
                    if value[key][0] == field:
                        del value[key]
                        return ldap.RES_DELETE, ''
            return ldap.RES_DELETE, ''


_NEXT = 1


class TestLDAPSQLAuth(unittest.TestCase):

    def tearDown(self):
        if not LDAP:
            return
        for key, user in list(users.items()):
            if user['uidNumber'] in (['-1'], ['0'], ['1']):
                continue
            del users[key]

    def _next_id(self):
        global _NEXT
        _NEXT += 1
        return _NEXT

    def _get_auth(self, **kw):
        if 'create_tables' not in kw:
            kw['create_tables'] = True
        auth = LDAPAuth('ldap://localhost', 'sqlite:///:memory:',
                        admin_user='uid=adminuser,ou=users,dc=mozilla',
                        admin_password='admin',
                        bind_user='uid=binduser,ou=users,dc=mozilla',
                        bind_password='bind',
                        connector_cls=MemoryStateConnector,
                        **kw)
        auth._get_next_user_id = self._next_id
        return auth

    def test_ldap_auth(self):
        if not LDAP:
            return

        auth = self._get_auth()
        if auth.get_user_id('tarek') is None:
            auth.create_user('tarek', u'tareké', 'tarek@ziade.org')
        uid = auth.get_user_id('tarek')

        auth_uid = auth.authenticate_user('tarek', u'tareké')
        self.assertEquals(auth_uid, uid)

        # reset code APIs
        code = auth.generate_reset_code(uid)
        self.assertFalse(auth.verify_reset_code(uid, 'beh'))
        self.assertFalse(auth.verify_reset_code(uid, 'XXXX-XXXX-XXXX-XXXX'))
        self.assertTrue(auth.verify_reset_code(uid, code))
        auth.clear_reset_code(uid)
        self.assertFalse(auth.verify_reset_code(uid, code))

        # e-mail update
        self.assertTrue(auth.update_email(uid, 'new@email.com', u'tareké'))
        name, email = auth.get_user_info(uid)
        self.assertEquals(email, 'new@email.com')
        self.assertEquals(name, 'tarek')

        # update password
        auth.update_password(uid, u'xxxxé', 'tarek')
        #auth_uid = auth.authenticate_user('tarek', 'tarek')
        #self.assertEquals(auth_uid, None)
        #auth_uid = auth.authenticate_user('tarek', 'xxxx')
        #self.assertEquals(auth_uid, ui)
        auth.delete_user(uid, u'xxxxé')
        auth_uid = auth.authenticate_user('tarek', u'xxxxé')
        self.assertEquals(auth_uid, None)

    def test_node_attribution(self):
        if not LDAP:
            return

        # let's set up some nodes in the SQL DB
        auth = self._get_auth()

        sql = ('insert into available_nodes '
               '(node, available_assignments, actives, downed) '
                'values("%s", %d, %d, %d)')

        for node, ct, actives, downed in (('node1', 10, 101, 0),
                                          ('node2', 0, 100,  0),
                                          ('node3', 1, 89, 0)):

            auth._engine.execute(sql % (node, ct, actives, downed))

        self._create_user(auth, 'tarek6', 'tarek6', 'tarek@ziade.org')
        uid = auth.get_user_id('tarek6')

        # first call will set it up
        self.assertEquals(auth.get_user_node(uid), 'https://node3/')
        self.assertEquals(auth.get_user_node(uid), 'https://node3/')

        # node3 is full now. Next user should be on node1
        self._create_user(auth, 'tarek2', 'tarek2', 'tarek@ziade.org')
        uid = auth.get_user_id('tarek2')

        # make sure we don't get a node if we ask not to give a new one
        self.assertEquals(auth.get_user_node(uid, False), None)
        self.assertEquals(auth.get_user_node(uid), 'https://node1/')

    def test_md5_dn(self):
        if not LDAP:
            return

        auth = self._get_auth(users_base_dn='ou=users,dc=mozilla')
        wanted = 'uidNumber=1,ou=users,dc=mozilla'
        self.assertEquals(auth._username2dn('testuser'), wanted)
        self.assertEquals(auth._userid2dn(1), wanted)

        auth.create_user('tarek', 'tarek', 'tarek@ziade.org')
        uid = auth.get_user_id('tarek')
        auth_uid = auth.authenticate_user('tarek', 'tarek')
        self.assertEquals(auth_uid, uid)
        self.assertTrue(auth.update_password(uid, 'xxxx', 'tarek'))

    def _create_user(self, auth, user_name, password, email):
        from services.auth.ldapsql import ssha, random, sha1
        user_name = str(user_name)
        user_id = auth._get_next_user_id()
        password_hash = ssha(password)
        key = '%s%s' % (random.randint(0, 9999999), user_name)
        key = sha1(key).hexdigest()

        user = {'cn': user_name,
                'sn': user_name,
                'uid': user_name,
                'uidNumber': str(user_id),
                'primaryNode': 'weave:',
                'rescueNode': 'weave:',
                'userPassword': password_hash,
                'account-enabled': 'Yes',
                'mail': email,
                'mail-verified': key,
                'objectClass': ['dataStore', 'inetOrgPerson']}

        user = user.items()
        dn = "uidNumber=%i,ou=users,dc=mozilla" % (user_id)

        with auth._conn(auth.admin_user, auth.admin_password) as conn:
            try:
                res, __ = conn.add_s(dn, user)
            except ldap.TIMEOUT:
                raise BackendTimeoutError()

        return res == ldap.RES_ADD

    def test_no_disabled_check(self):
        if not LDAP:
            return

        auth = self._get_auth(users_base_dn='dc=mozilla',
                              check_account_state=False)
        self._create_user(auth, 'x', 'xxxx', 'tarek@ziade.org')
        uid = auth.authenticate_user('x', 'xxxx')
        self.assertTrue(uid is not None)

    def test_ldap_pool_size(self):
        if not LDAP:
            return

        auth = self._get_auth(ldap_pool_size=5)
        self.assertEqual(auth.conn.size, 5)

    def test_update_password(self):
        # when admin_update_password is called with a key
        # the admin auth should be used.
        #
        # When update_password is called with the user password,
        # the bind should be the user
        if not LDAP:
            return

        auth = self._get_auth(ldap_pool_size=5)
        calls = []
        auth._conn2 = auth._conn

        def conn(bind=None, passwd=None):
            calls.append((bind, passwd))
            return auth._conn2(bind, passwd)

        old = auth.verify_reset_code
        auth.verify_reset_code = lambda userid, key: True
        auth._conn = conn
        try:
            self._create_user(auth, 'tarek4', 'tarek4', 'tarek@ziade.org')
            uid = auth.authenticate_user('tarek4', 'tarek4')
            self.assertTrue(auth.admin_update_password(uid, 'password', 'key'))
            self.assertEqual(calls[-1], ('uid=adminuser,ou=users,dc=mozilla',
                                         'admin'))

            self.assertTrue(auth.update_password(uid, 'password2', 'password'))
            self.assertEqual(calls[-1],
                       ('uidNumber=%s,ou=users,dc=mozilla' % uid, 'password'))
        finally:
            auth._conn = auth._conn2
            auth.verify_reset_code = old

    def test_pool_purged(self):
        if not LDAP:
            return

        # when a user is deleted or its password changed, any previous
        # connection in the pool that has his binding must be purged

        # IOW, the user should not be able to keep a valid connection
        # with an old password
        auth = self._get_auth(ldap_pool_size=5)
        self._create_user(auth, 'joe', 'joe', 'tarek@ziade.org')
        uid = auth.authenticate_user('joe', 'joe')
        self.assertTrue(auth.update_password(uid, 'newpassword',
                        old_password='joe'))

        # using the old password should not work anymore
        uid = auth.authenticate_user('joe', 'joe')
        self.assertTrue(uid is None)

        # using the new password should work
        uid = auth.authenticate_user('joe', 'newpassword')
        self.assertTrue(uid is not None)

        # let's delete the user
        auth.delete_user(uid, 'newpassword')

        # using the new password should not work anymore
        uid = auth.authenticate_user('joe', 'newpassword')
        self.assertTrue(uid is None)

        # and the pool should not contain any joe left
        pool = [conn.who for conn in auth.conn._pool]
        self.assertTrue('uid=joe,ou=users,dc=mozilla' not in pool)

    def test_get_user_id_fail(self):
        if not LDAP:
            return

        auth = self._get_auth(users_base_dn='dc=mozilla',
                              check_account_state=False)

        self._create_user(auth, 'tarek', 'tarek', 'tarek@ziade.org')
        uid = auth.get_user_id('tarek')
        self.assertTrue(uid is not None)

        # now with a search_st failure
        from ldap import TIMEOUT

        old = MemoryStateConnector.search_st

        def _search(*arg, **kw):
            raise TIMEOUT

        MemoryStateConnector.search_st = _search
        try:
            self.assertRaises(BackendError, auth.get_user_id, 'tarek')
        finally:
            MemoryStateConnector.search_st = old

    def test_ldap_no_pool(self):
        if not LDAP:
            return

        name = 'user123'

        # making sure we support the no-pool mode
        auth = self._get_auth(no_pool=True)

        # creating account
        self._create_user(auth, name, 'tarek', 'tarek@ziade.org')
        uid = auth.get_user_id(name)
        self.assertTrue(uid is not None)

        # auth
        auth_uid = auth.authenticate_user(name, 'tarek')
        self.assertEquals(auth_uid, uid)

        # e-mail update
        self.assertTrue(auth.update_email(uid, 'new@email.com', 'tarek'))
        wanted_name, email = auth.get_user_info(uid)
        self.assertEquals(email, 'new@email.com')
        self.assertEquals(wanted_name, name)

        # update password
        auth.update_password(uid, 'xxxx', old_password='tarek')

        # auth again
        auth_uid = auth.authenticate_user(name, 'xxxx')
        self.assertEquals(auth_uid, uid)

        # the old auth fails
        auth_uid = auth.authenticate_user(name, 'tarek')
        self.assertTrue(auth_uid is None)

        # delete account
        auth.delete_user(uid, 'xxxx')
        auth_uid = auth.authenticate_user(name, 'xxxx')
        self.assertEquals(auth_uid, None)

    def test_no_creation(self):
        if not LDAP:
            return

        # this should not create any table in the DB
        auth = self._get_auth(create_tables=False)
        self.assertRaises(OperationalError, auth._engine.execute,
                          'select * from available_nodes')

        # this should
        auth = self._get_auth(create_tables=True)
        res = auth._engine.execute('select * from available_nodes').fetchall()
        self.assertEquals(res, [])

    def test_not_implemented(self):
        if not LDAP:
            return
        auth = LDAPAuth('ldap://localhost', 'sqlite:///:memory:')

        self.assertRaises(NotImplementedError, auth.update_email, 'tarek',
                          'email')
