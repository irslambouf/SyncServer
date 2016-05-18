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
"""
SQL backend for syncserver.

This module implements an SQL storage plugin for syncserver.  In the simplest
use case it consists of three database tables:

  users:        user ids and authentication details (imported from server-core)
  collections:  the names of per-user custom collections
  wbo:          the individual WBO items stored in each collection

For efficiency when dealing with large datasets, the plugin also supports
sharding of the WBO items into multiple tables named "wbo0" through "wboN".
This behaviour is off by default; pass shard=True to enable it.

For details of the database schema, see the file "sqlmappers.py".
For details of the prepared queries, see the file "queries.py".

"""

import urlparse
from time import time
from collections import defaultdict

import sqlalchemy.event
from sqlalchemy.sql import (text as sqltext, select, bindparam, insert, update,
                            and_)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.expression import _generative, Delete, _clone, ClauseList
from sqlalchemy import util
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.util import queue as sqla_queue
from sqlalchemy.pool import NullPool, QueuePool

from metlog.decorators.stats import timeit as metlog_timeit
from metlog.holder import CLIENT_HOLDER

from syncstorage.storage import StorageConflictError
from syncstorage.storage.queries import get_query
from syncstorage.storage.sqlmappers import (tables, users, collections,
                                            get_wbo_table_name, MAX_TTL,
                                            get_wbo_table,
                                            get_wbo_table_byindex)
from syncstorage.storage.sqlmappers import wbo as _wbo
from services.util import (time2bigint, bigint2time, round_time,
                           safe_execute, create_engine)
from syncstorage.wbo import WBO


METLOG_PREFIX = 'syncstorage.storage.sql.'

sql_timer_name = METLOG_PREFIX + 'timed_safe_execute'
timed_safe_execute = metlog_timeit(sql_timer_name)(safe_execute)

_KB = float(1024)

# For efficiency, it's possible to use fixed pre-determined IDs for
# common collection names.  This is the canonical list of such names.
# Non-standard collections will be allocated IDs starting from the
# highest ID in this collection.
#
# The original set of collection names was buggy, having "client" and "key"
# rather than "clients" and "keys".  We have to keep it for backwards compat
# reasons, but new deploys should use the "fixed" set of keys.
#
# See https://bugzilla.mozilla.org/show_bug.cgi?id=688623 for details.
#
STANDARD_COLLECTIONS = {1: 'client', 2: 'crypto', 3: 'forms', 4: 'history',
                        5: 'key', 6: 'meta', 7: 'bookmarks', 8: 'prefs',
                        9: 'tabs', 10: 'passwords'}

STANDARD_COLLECTIONS_NAMES = dict((value, key) for key, value in
                                   STANDARD_COLLECTIONS.items())

FIXED_COLLECTIONS = {1: 'clients', 2: 'crypto', 3: 'forms', 4: 'history',
                     5: 'keys', 6: 'meta', 7: 'bookmarks', 8: 'prefs',
                     9: 'tabs', 10: 'passwords', 11: 'addons'}

FIXED_COLLECTIONS_NAMES = dict((value, key) for key, value in
                                FIXED_COLLECTIONS.items())

def _roundedbigint(value):
    return time2bigint(round_time(value))


def _int_now():
    return int(time())


class _CustomCompiler(SQLCompiler):
    """SQLAlchemy statement compiler to support DELETE with ORDER BY and LIMIT.

    The visit_delete() method of this class is mostly a verbatim copy of the
    method from SQLCompiler, but has extra logic to handle ORDER BY and LIMIT
    clauses on the delete statement.
    """

    def visit_delete(self, delete_stmt):
        self.stack.append({'from': set([delete_stmt.table])})
        self.isdelete = True

        text = "DELETE FROM " + self.preparer.format_table(delete_stmt.table)

        if delete_stmt._returning:
            self.returning = delete_stmt._returning
            if self.returning_precedes_values:
                text += " " + self.returning_clause(delete_stmt,
                                                    delete_stmt._returning)

        if delete_stmt._whereclause is not None:
            text += " WHERE " + self.process(delete_stmt._whereclause)

        if len(delete_stmt._order_by_clause) > 0:
            text += " ORDER BY " + self.process(delete_stmt._order_by_clause)

        if delete_stmt._limit is not None or delete_stmt._offset is not None:
            text += self.limit_clause(delete_stmt)

        if self.returning and not self.returning_precedes_values:
            text += " " + self.returning_clause(delete_stmt,
                                                delete_stmt._returning)

        self.stack.pop(-1)

        return text


class _DeleteOrderBy(Delete):
    """Custom Delete statement with ORDER BY and LIMIT support."""

    def __init__(self, table, whereclause, bind=None, returning=None,
                 order_by=None, limit=None, offset=None, **kwargs):
        Delete.__init__(self, table, whereclause, bind, returning, **kwargs)
        self._order_by_clause = ClauseList(*util.to_list(order_by) or [])
        self._limit = limit
        self._offset = offset

    @_generative
    def order_by(self, *clauses):
        self.append_order_by(*clauses)

    def append_order_by(self, *clauses):
        if len(clauses) == 1 and clauses[0] is None:
            self._order_by_clause = ClauseList()
        else:
            if getattr(self, '_order_by_clause', None) is not None:
                clauses = list(self._order_by_clause) + list(clauses)
            self._order_by_clause = ClauseList(*clauses)

    @_generative
    def limit(self, limit):
        self._limit = limit

    @_generative
    def offset(self, offset):
        self._offset = offset

    def _copy_internals(self, clone=_clone):
        self._whereclause = clone(self._whereclause)
        for attr in ('_order_by_clause',):
            if getattr(self, attr) is not None:
                setattr(self, attr, clone(getattr(self, attr)))

    def get_children(self, column_collections=True, **kwargs):
        children = Delete.get_children(column_collections, **kwargs)
        return children + [self._order_by_clause]

    def _compiler(self, dialect, **kw):
        return _CustomCompiler(dialect, self, **kw)


def _delete(table, whereclause=None, **kwargs):
    return _DeleteOrderBy(table, whereclause, **kwargs)


class _QueueWithMaxBacklog(sqla_queue.Queue):
    """SQLAlchemy Queue subclass with a limit on the length of the backlog.

    This base Queue class sets no limit on the number of threads that can be
    simultaneously blocked waiting for an item on the queue.  This class
    adds a "max_backlog" parameter that can be used to bound this number.
    """

    def __init__(self, maxsize=0, max_backlog=-1):
        self.max_backlog = max_backlog
        self.cur_backlog = 0
        sqla_queue.Queue.__init__(self, maxsize)

    def get(self, block=True, timeout=None):
        # The SQLAlchemy Queue class uses a re-entrant mutext by default,
        # so it's safe to acquire it both here and in the superclass method.
        with self.mutex:
            backlog_exceeded = False
            self.cur_backlog += 1
            try:
                # Only allow a blocking get() if it won't exceed max backlog.
                if self.max_backlog >= 0:
                    if self.cur_backlog > self.max_backlog:
                        backlog_exceeded = True
                        block = False
                        timeout = None
                return sqla_queue.Queue.get(self, block, timeout)
            except sqla_queue.Empty:
                # Collect statistics on attempts that time out, and attempts
                # that fail immediately due to excess backlog.  They both
                # give the same exception, so we need a flag to differentiate.
                if backlog_exceeded:
                    counter_name = METLOG_PREFIX + 'pool.backlog_exceeded'
                else:
                    counter_name = METLOG_PREFIX + 'pool.timeout'
                CLIENT_HOLDER.default_client.incr(counter_name)
                raise
            finally:
                self.cur_backlog -= 1


class QueuePoolWithMaxBacklog(QueuePool):
    """An SQLAlchemy QueuePool with a limit on the length of the backlog.

    The base QueuePool class sets no limit on the number of threads that can
    be simultaneously attempting to connect to the database.  This means that
    a misbehaving database can easily lock up all threads by keeping them
    waiting in the queue.

    This QueuePool subclass provides a "max_backlog" that limits the number
    of threads that can be in the queue waiting for a connection.  Once this
    limit has been reached, any further attempts to acquire a connection will
    be rejected immediately.
    """

    def __init__(self, creator, max_backlog=-1, **kwds):
        # Wrap the creator callback with some metrics logging, unless it
        # has already been wrapped.
        if getattr(creator, "has_metlog_wrapper", False):
            logging_creator = creator
        else:
            def logging_creator(*args, **kwds):
                counter_name = METLOG_PREFIX + '.pool.new_connection'
                CLIENT_HOLDER.default_client.incr(counter_name)
                return creator(*args, **kwds)
            logging_creator.has_metlog_wrapper = True
        QueuePool.__init__(self, logging_creator, **kwds)
        self._pool = _QueueWithMaxBacklog(self._pool.maxsize, max_backlog)

    def recreate(self):
        CLIENT_HOLDER.default_client.incr(METLOG_PREFIX + 'pool.recreate')
        new_self = QueuePool.recreate(self)
        new_self._pool = _QueueWithMaxBacklog(self._pool.maxsize,
                                              self._pool.max_backlog)
        return new_self

    def dispose(self):
        CLIENT_HOLDER.default_client.incr(METLOG_PREFIX + 'pool.dispose')
        return QueuePool.dispose(self)

    @metlog_timeit(METLOG_PREFIX + 'pool.get')
    def _do_get(self):
        c = QueuePool._do_get(self)
        self.logger.debug("QueuePoolWithMaxBacklog status: %s", self.status())
        return c


SHARED_POOLS = {}


class SQLStorage(object):
    """Storage plugin implemented using an SQL database.

    This class implements the storage plugin API using SQLAlchemy.  You
    must specify the SQLAlchemy database URI string to connect to, and
    can customize behaviour with the following keyword arguments:

        * standard_collections:  use fixed pre-determined ids for common
                                 collection names
        * fixed_collections:     use the updated fixed pre-determined ids for
                                 common collection names
        * create_tables:         create the database tables if they don't
                                 exist at startup
        * use_quota/quota_size:  limit per-user storage to a specific quota
        * shard/shardsize:       enable sharding of the WBO table

    """

    def __init__(self, sqluri,
                 standard_collections=False, fixed_collections=False,
                 use_quota=False, quota_size=0, pool_size=100,
                 pool_recycle=60, reset_on_return=True, create_tables=False,
                 shard=False, shardsize=100,
                 pool_max_overflow=10, pool_max_backlog=-1, no_pool=False,
                 pool_timeout=30, use_shared_pool=False,
                 echo_pool=False, **kw):

        parsed_sqluri = urlparse.urlparse(sqluri)
        self.sqluri = sqluri
        self.driver = parsed_sqluri.scheme

        # Create the SQLAlchemy engine, using the given parameters for
        # connection pooling.  Pooling doesn't work properly for sqlite so
        # it's disabled for that driver regardless of the value of no_pool.
        # If use_shared_pool is True, then a single pool is used per db
        # hostname.
        if no_pool or self.driver == 'sqlite':
            self._engine = create_engine(sqluri, poolclass=NullPool,
                                         logging_name='syncserver')
        elif use_shared_pool and parsed_sqluri.hostname in SHARED_POOLS:
            pool = SHARED_POOLS[parsed_sqluri.hostname]
            self._engine = create_engine(sqluri, pool=pool,
                                         logging_name='syncserver')
        else:
            sqlkw = {
                'poolclass': QueuePoolWithMaxBacklog,
                'pool_size': int(pool_size),
                'pool_recycle': int(pool_recycle),
                'logging_name': 'syncserver',
                'pool_timeout': int(pool_timeout),
                'max_overflow': int(pool_max_overflow),
                'max_backlog': int(pool_max_backlog),
                'echo_pool': bool(echo_pool),
            }

            if self.driver in ('mysql', 'pymysql',
                               'mysql+mysqlconnector'):
                sqlkw['pool_reset_on_return'] = reset_on_return

            self._engine = create_engine(sqluri, **sqlkw)

        # If a shared pool is in use, set up an event listener to switch to
        # the proper database each time a query is executed.
        if use_shared_pool:
            if parsed_sqluri.hostname not in SHARED_POOLS:
                SHARED_POOLS[parsed_sqluri.hostname] = self._engine.pool

            def switch_db(conn, cursor, query, *junk):
                cursor.execute("use %s" % (self._engine.url.database,))

            sqlalchemy.event.listen(self._engine, 'before_cursor_execute',
                                    switch_db)

        # Bind the table metadata to our engine.
        # This is also a good time to create tables if they're missing.
        for table in tables:
            table.metadata.bind = self._engine
            if create_tables:
                table.create(checkfirst=True)
        self.engine_name = self._engine.name
        self.standard_collections = standard_collections
        self.fixed_collections = fixed_collections
        self.use_quota = use_quota
        self.quota_size = int(quota_size)
        self.shard = shard
        self.shardsize = shardsize
        if self.shard:
            for index in range(shardsize):
                table = get_wbo_table_byindex(index)
                table.metadata.bind = self._engine
                if create_tables:
                    table.create(checkfirst=True)
        else:
            _wbo.metadata.bind = self._engine
            if create_tables:
                _wbo.create(checkfirst=True)

        # If using a fixed set of collection names, take
        # a local reference to the appropriate set.
        if standard_collections:
            if fixed_collections:
                err = "Can't use both standard and fixed collection names"
                raise ValueError(msg)
            self._collections_by_id = STANDARD_COLLECTIONS
            self._collections_by_name = STANDARD_COLLECTIONS_NAMES
        elif fixed_collections:
            self._collections_by_id = FIXED_COLLECTIONS
            self._collections_by_name = FIXED_COLLECTIONS_NAMES
        else:
            self._collections_by_id = None
            self._collections_by_name = None

        # A per-user cache for collection metadata.
        # This is to avoid looking up the collection name <=> id mapping
        # in the database on every request.
        self._temp_cache = defaultdict(dict)

    @property
    def logger(self):
        return CLIENT_HOLDER.default_client

    @classmethod
    def get_name(cls):
        """Return the name of the storage plugin"""
        return 'sql'

    def is_healthy(self):
        """Check whether the backend is healthy and active."""
        # This executes a real query but, since there's no user with id zero,
        # there will be no rows in the result.
        self.collection_exists(0, "test_collection")
        return True

    def _do_query(self, *args, **kwds):
        """Execute a database query, returning the rowcount."""
        res = timed_safe_execute(self._engine, *args, **kwds)
        try:
            return res.rowcount
        finally:
            res.close()

    def _do_query_fetchone(self, *args, **kwds):
        """Execute a database query, returning the first result."""
        res = timed_safe_execute(self._engine, *args, **kwds)
        try:
            return res.fetchone()
        finally:
            res.close()

    def _do_query_fetchall(self, *args, **kwds):
        """Execute a database query, returning iterator over the results."""
        res = timed_safe_execute(self._engine, *args, **kwds)
        try:
            for row in res:
                yield row
        finally:
            res.close()

    #
    # Users APIs
    #
    def _get_query(self, name, user_id):
        """Get the named pre-built query, sharding by user_id if necessary."""
        if self.shard:
            return get_query(name, user_id)
        return get_query(name)

    def user_exists(self, user_id):
        """Returns true if the user exists."""
        query = self._get_query('USER_EXISTS', user_id)
        res = self._do_query_fetchone(query, user_id=user_id)
        return res is not None

    def set_user(self, user_id, **values):
        """set information for a user. values contains the fields to set.

        If the user doesn't exists, it will be created.
        """
        values['id'] = user_id
        if not self.user_exists(user_id):
            query = insert(users).values(**values)
        else:
            query = update(users).where(users.c.id == user_id)
            query = query.values(**values)
        self._do_query(query)

    def get_user(self, user_id, fields=None):
        """Returns user information.

        If fields is provided, it is a list of fields to return
        """
        if fields is None:
            fields = [users]
        else:
            fields = [getattr(users.c, field) for field in fields]

        query = select(fields, users.c.id == user_id)
        return self._do_query_fetchone(query)

    def delete_user(self, user_id):
        """Removes a user (and all its data)"""
        for query in ('DELETE_USER_WBOS', 'DELETE_USER_COLLECTIONS',
                      'DELETE_USER'):
            query = self._get_query(query, user_id)
            self._do_query(query, user_id=user_id)

    def _get_collection_id(self, user_id, collection_name, create=True):
        """Returns a collection id, given the name."""
        if self._collections_by_name is not None:
            if collection_name in self._collections_by_name:
                return self._collections_by_name[collection_name]

        # custom collection
        data = self.get_collection(user_id, collection_name,
                                   ['collectionid'], create)
        if data is None:
            return None

        return data['collectionid']

    def delete_storage(self, user_id):
        """Removes all user data"""
        for query in ('DELETE_USER_WBOS', 'DELETE_USER_COLLECTIONS'):
            query = self._get_query(query, user_id)
            self._do_query(query, user_id=user_id)
        # XXX see if we want to check the rowcount
        return True

    #
    # Collections APIs
    #

    def delete_collection(self, user_id, collection_name):
        """deletes a collection"""
        if not self.collection_exists(user_id, collection_name):
            return

        # removing items first
        self.delete_items(user_id, collection_name)

        # then the collection
        query = self._get_query('DELETE_USER_COLLECTION', user_id)
        return self._do_query(query, user_id=user_id,
                              collection_name=collection_name)

    def collection_exists(self, user_id, collection_name):
        """Returns True if the collection exists"""
        query = self._get_query('COLLECTION_EXISTS', user_id)
        res = self._do_query_fetchone(query, user_id=user_id,
                                      collection_name=collection_name)
        return res is not None

    def set_collection(self, user_id, collection_name, **values):
        """Creates a collection"""
        # XXX values is not used for now because there are no values besides
        # the name
        if self.collection_exists(user_id, collection_name):
            return

        values['userid'] = user_id
        values['name'] = collection_name

        if self._collections_by_id is not None:
            min_id = 100
        else:
            min_id = 0

        # getting the max collection_id
        # XXX why don't we have an autoinc here ?
        # see https://bugzilla.mozilla.org/show_bug.cgi?id=579096
        next_id = -1
        while next_id < min_id:
            query = self._get_query('COLLECTION_NEXTID', user_id)
            max_ = self._do_query_fetchone(query, user_id=user_id)
            if max_[0] is None:
                next_id = min_id
            else:
                next_id = max_[0] + 1

        # insertion
        values['collectionid'] = next_id
        query = insert(collections).values(**values)
        self._do_query(query, **values)
        return next_id

    def get_collection(self, user_id, collection_name, fields=None,
                       create=True):
        """Return information about a collection."""
        if fields is None:
            fields = [collections]
            field_names = collections.columns.keys()
        else:
            field_names = fields
            fields = [getattr(collections.c, field) for field in fields]

        query = select(fields, and_(collections.c.userid == user_id,
                                    collections.c.name == collection_name))
        res = self._do_query_fetchone(query)

        # the collection is created
        if res is None and create:
            collid = self.set_collection(user_id, collection_name)
            res = {'userid': user_id, 'collectionid': collid,
                   'name': collection_name}
            if fields is not None:
                for key in res.keys():
                    if key not in field_names:
                        del res[key]
        elif res is not None:
            # make this a single step
            res = dict([(key, value) for key, value in res.items()
                         if value is not None])
        return res

    def get_collections(self, user_id, fields=None):
        """returns the collections information """
        if fields is None:
            fields = [collections]
        else:
            fields = [getattr(collections.c, field) for field in fields]

        query = select(fields, collections.c.userid == user_id)
        return list(self._do_query_fetchall(query))

    def get_collection_names(self, user_id):
        """return the collection names for a given user"""
        query = self._get_query('USER_COLLECTION_NAMES', user_id)
        names = self._do_query_fetchall(query, user_id=user_id)
        return [(res[0], res[1]) for res in names]

    def get_collection_timestamps(self, user_id):
        """return the collection names for a given user"""
        query = 'COLLECTION_STAMPS'
        query = self._get_query(query, user_id)
        res = self._do_query_fetchall(query, user_id=user_id)
        try:
            return dict([(self._collid2name(user_id, coll_id),
                        bigint2time(stamp)) for coll_id, stamp in res])
        finally:
            self._purge_cache(user_id)

    def _cache(self, user_id, name, func):
        user_cache = self._temp_cache[user_id]
        if name in user_cache:
            return user_cache[name]
        data = func()
        user_cache[name] = data
        return data

    def _purge_cache(self, user_id):
        self._temp_cache.pop(user_id, None)

    def _collid2name(self, user_id, collection_id):
        if self._collections_by_id is not None:
            if collection_id in self._collections_by_id:
                return self._collections_by_id[collection_id]

        # custom collections
        def _coll():
            data = self.get_collection_names(user_id)
            return dict(data)

        collections = self._cache(user_id, 'collection_names', _coll)
        try:
            return collections[collection_id]
        except KeyError:
            msg = "User %d collection %d has no collection name."
            msg += "  Possible database corruption?"
            raise KeyError(msg % (user_id, collection_id))

    def get_collection_counts(self, user_id):
        """Return the collection counts for a given user"""
        query = self._get_query('COLLECTION_COUNTS', user_id)
        res = self._do_query_fetchall(query, user_id=user_id, ttl=_int_now())
        try:
            return dict([(self._collid2name(user_id, collid), count)
                          for collid, count in res])
        finally:
            self._purge_cache(user_id)

    def get_collection_max_timestamp(self, user_id, collection_name):
        """Returns the max timestamp of a collection."""
        query = self._get_query('COLLECTION_MAX_STAMPS', user_id)
        collection_id = self._get_collection_id(user_id, collection_name)
        res = self._do_query_fetchone(query, user_id=user_id,
                                      collection_id=collection_id)
        stamp = res[0]
        if stamp is None:
            return None
        return bigint2time(stamp)

    def get_collection_sizes(self, user_id):
        """Returns the total size in KB for each collection of a user storage.

        The size is the sum of stored payloads.
        """
        query = self._get_query('COLLECTIONS_STORAGE_SIZE', user_id)
        res = self._do_query_fetchall(query, user_id=user_id, ttl=_int_now())
        try:
            return dict([(self._collid2name(user_id, col[0]),
                        int(col[1]) / _KB) for col in res])
        finally:
            self._purge_cache(user_id)

    #
    # Items APIs
    #
    def item_exists(self, user_id, collection_name, item_id):
        """Returns a timestamp if an item exists."""
        collection_id = self._get_collection_id(user_id, collection_name)
        query = self._get_query('ITEM_EXISTS', user_id)
        res = self._do_query_fetchone(query, user_id=user_id, item_id=item_id,
                                      collection_id=collection_id)
        if res is None:
            return None
        return bigint2time(res[0])

    def _get_wbo_table(self, user_id):
        if self.shard:
            return get_wbo_table(user_id, self.shardsize)
        return _wbo

    def get_items(self, user_id, collection_name, fields=None, filters=None,
                  limit=None, offset=None, sort=None):
        """returns items from a collection

        "filter" is a dict used to add conditions to the db query.
        Its keys are the field names on which the condition operates.
        Its values are the values the field should have.
        It can be a single value, or a list. For the latter the in()
        operator is used. For single values, the operator has to be provided.
        """
        wbo = self._get_wbo_table(user_id)
        collection_id = self._get_collection_id(user_id, collection_name)
        if fields is None:
            fields = [wbo]
        else:
            fields = [getattr(wbo.c, field) for field in fields]

        # preparing the where statement
        where = [wbo.c.username == user_id,
                 wbo.c.collection == collection_id]

        if filters is not None:
            for field, value in filters.items():
                field = getattr(wbo.c, field)

                operator, value = value
                if field.name == 'modified':
                    value = _roundedbigint(value)

                if isinstance(value, (list, tuple)):
                    where.append(field.in_(value))
                else:
                    if operator == '=':
                        where.append(field == value)
                    elif operator == '<':
                        where.append(field < value)
                    elif operator == '>':
                        where.append(field > value)

        if filters is None or 'ttl' not in filters:
            where.append(wbo.c.ttl > _int_now())

        where = and_(*where)
        query = select(fields, where)

        if sort is not None:
            if sort == 'oldest':
                query = query.order_by(wbo.c.modified.asc())
            elif sort == 'newest':
                query = query.order_by(wbo.c.modified.desc())
            else:
                query = query.order_by(wbo.c.sortindex.desc())

        if limit is not None and int(limit) > 0:
            query = query.limit(int(limit))

        if offset is not None and int(offset) > 0:
            query = query.offset(int(offset))

        res = self._do_query_fetchall(query)
        converters = {'modified': bigint2time}
        return [WBO(line, converters) for line in res]

    def get_item(self, user_id, collection_name, item_id, fields=None):
        """returns one item"""
        wbo = self._get_wbo_table(user_id)
        collection_id = self._get_collection_id(user_id, collection_name)
        if fields is None:
            fields = [wbo]
        else:
            fields = [getattr(wbo.c, field) for field in fields]
        where = self._get_query('ITEM_ID_COL_USER', user_id)
        query = select(fields, where)
        res = self._do_query_fetchone(query, user_id=user_id, item_id=item_id,
                                      collection_id=collection_id,
                                      ttl=_int_now())
        if res is None:
            return None

        return WBO(res, {'modified': bigint2time})

    def _set_item(self, user_id, collection_name, item_id, **values):
        """Adds or update an item"""
        wbo = self._get_wbo_table(user_id)

        if 'modified' in values:
            values['modified'] = _roundedbigint(values['modified'])

        if 'ttl' not in values:
            values['ttl'] = MAX_TTL
        else:
            # ttl is provided in seconds, so we add it
            # to the current timestamp
            values['ttl'] += _int_now()

        modified = self.item_exists(user_id, collection_name, item_id)

        if 'payload' in values:
            values['payload_size'] = len(values['payload'])

        collection_id = self._get_collection_id(user_id,
                                                collection_name)

        if modified is None:   # does not exists
            values['collection'] = collection_id
            values['id'] = item_id
            values['username'] = user_id
            query = insert(wbo).values(**values)
        else:
            if 'id' in values:
                del values['id']
            key = and_(wbo.c.id == item_id, wbo.c.username == user_id,
                       wbo.c.collection == collection_id)
            query = update(wbo).where(key).values(**values)

        try:
            self._do_query(query)
        except IntegrityError:
            raise StorageConflictError()

        if 'modified' in values:
            return bigint2time(values['modified'])

        return modified

    def set_item(self, user_id, collection_name, item_id, storage_time=None,
                 **values):
        """Adds or update an item"""
        if storage_time is None:
            storage_time = round_time()

        if 'payload' in values and 'modified' not in values:
            values['modified'] = storage_time

        return self._set_item(user_id, collection_name, item_id, **values)

    def _get_wbo_table_name(self, user_id):
        if self.shard:
            return get_wbo_table_name(user_id)
        return 'wbo'

    def set_items(self, user_id, collection_name, items, storage_time=None):
        """Adds or update a batch of items.

        Returns a list of success or failures.
        """
        if storage_time is None:
            storage_time = round_time()

        if self.engine_name in ('sqlite', 'postgresql'):
            count = 0
            for item in items:
                if 'id' not in item:
                    continue
                item_id = item['id']
                item['modified'] = storage_time
                self.set_item(user_id, collection_name, item_id, **item)
                count += 1
            return count

        # XXX See if SQLAlchemy knows how to do batch inserts
        # that's quite specific to mysql
        fields = ('id', 'parentid', 'predecessorid', 'sortindex', 'modified',
                  'payload', 'payload_size', 'ttl')

        table = self._get_wbo_table_name(user_id)
        query = 'insert into %s (username, collection, %s) values ' \
                    % (table, ','.join(fields))

        values = {}
        values['collection'] = self._get_collection_id(user_id,
                                                       collection_name)
        values['user_id'] = user_id

        # building the values batch
        binds = [':%s%%(num)d' % field for field in fields]
        pattern = '(:user_id,:collection,%s) ' % ','.join(binds)

        lines = []
        for num, item in enumerate(items):
            lines.append(pattern % {'num': num})
            for field in fields:
                value = item.get(field)
                if value is None:
                    continue
                if field == 'modified' and value is not None:
                    value = _roundedbigint(storage_time)
                values['%s%d' % (field, num)] = value

            if ('payload%d' % num in values and
                'modified%d' % num not in values):
                values['modified%d' % num] = _roundedbigint(storage_time)

            if values.get('ttl%d' % num) is None:
                values['ttl%d' % num] = 2100000000
            else:
                values['ttl%d' % num] += int(storage_time)

            if 'payload%d' % num in values:
                size = len(values['payload%d' % num])
                values['payload_size%d' % num] = size

        query += ','.join(lines)

        # allowing updates as well
        query += (' on duplicate key update parentid = values(parentid),'
                  'predecessorid = values(predecessorid),'
                  'sortindex = values(sortindex),'
                  'modified = values(modified), payload = values(payload),'
                  'payload_size = values(payload_size),'
                  'ttl = values(ttl)')
        return self._do_query(sqltext(query), **values)

    def delete_item(self, user_id, collection_name, item_id,
                    storage_time=None):
        """Deletes an item"""
        collection_id = self._get_collection_id(user_id, collection_name,
                                                create=False)
        if collection_id is None:
            return False

        query = self._get_query('DELETE_SOME_USER_WBO', user_id)
        rowcount = self._do_query(query, user_id=user_id, item_id=item_id,
                                  collection_id=collection_id)
        return rowcount == 1

    def delete_items(self, user_id, collection_name, item_ids=None,
                     filters=None, limit=None, offset=None, sort=None,
                     storage_time=None):
        """Deletes items. All items are removed unless item_ids is provided"""
        collection_id = self._get_collection_id(user_id, collection_name,
                                                create=False)
        if collection_id is None:
            return False

        wbo = self._get_wbo_table(user_id)
        query = _delete(wbo)
        where = [wbo.c.username == bindparam('user_id'),
                 wbo.c.collection == bindparam('collection_id')]

        if item_ids is not None:
            where.append(wbo.c.id.in_(item_ids))

        if filters is not None:
            for field, value in filters.items():
                field = getattr(wbo.c, field)

                operator, value = value
                if field.name == 'modified':
                    value = _roundedbigint(value)
                if isinstance(value, (list, tuple)):
                    where.append(field.in_(value))
                else:
                    if operator == '=':
                        where.append(field == value)
                    elif operator == '<':
                        where.append(field < value)
                    elif operator == '>':
                        where.append(field > value)

        where = and_(*where)
        query = query.where(where)

        if self.engine_name != 'sqlite':
            if sort is not None:
                if sort == 'oldest':
                    query = query.order_by(wbo.c.modified.asc())
                elif sort == 'newest':
                    query = query.order_by(wbo.c.modified.desc())
                else:
                    query = query.order_by(wbo.c.sortindex.desc())

            if limit is not None and int(limit) > 0:
                query = query.limit(int(limit))

            if offset is not None and int(offset) > 0:
                query = query.offset(int(offset))

        # XXX see if we want to send back more details
        # e.g. by checking the rowcount
        rowcount = self._do_query(query, user_id=user_id,
                                  collection_id=collection_id)
        return rowcount > 0

    def get_total_size(self, user_id, recalculate=False):
        """Returns the total size in KB of a user storage.

        The size is the sum of stored payloads.
        """
        query = self._get_query('USER_STORAGE_SIZE', user_id)
        res = self._do_query_fetchone(query, user_id=user_id, ttl=_int_now())
        if res is None or res[0] is None:
            return 0.0
        return int(res[0]) / _KB

    def get_size_left(self, user_id, recalculate=False):
        """Returns the storage left for a user"""
        return self.quota_size - self.get_total_size(user_id, recalculate)
