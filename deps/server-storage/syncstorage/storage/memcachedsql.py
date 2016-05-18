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
Memcached + SQL backend

- User tabs are stored in one single "user_id:tabs" key
- The total storage size is stored in "user_id:size"
- The meta/global wbo is stored in "user_id"
- The info/collections timestamp mapping is stored in "user_id:stamps"
"""
import time
import simplejson as json

from sqlalchemy.sql import select, bindparam, func

from services.util import round_time

from syncstorage.storage.sql import SQLStorage
from syncstorage.storage.sqlmappers import wbo
from syncstorage.storage.cachemanager import (CacheManager,
                                              MirroredCacheManager,
                                              _key)

# Recalculate quota at most once per hour.
QUOTA_RECALCULATION_PERIOD = 60 * 60

_COLLECTION_LIST = select([wbo.c.collection, func.max(wbo.c.modified),
                           func.count(wbo)],
            wbo.c.username == bindparam('user_id')).group_by(wbo.c.collection)


# XXX suboptimal: creates an object on every dump/load call
# but that's how python-memcached works - using a class
# instead of an object would not be thread-safe.
#
# Need to ask Sean to improve this
class _JSONDumper(object):
    """Dumps and loads json in a file-like object"""
    def __init__(self, file, protocol=0):
        self.file = file

    def dump(self, val):
        self.file.write(json.dumps(val, use_decimal=True))

    def load(self):
        return json.loads(self.file.read())


class MemcachedSQLStorage(SQLStorage):
    """Uses Memcached when possible/useful, SQL otherwise.
    """

    def __init__(self, sqluri,
                 standard_collections=False, fixed_collections=False,
                 use_quota=False, quota_size=0, pool_size=100,
                 pool_recycle=3600, cache_servers=None,
                 mirrored_cache_servers=None,
                 create_tables=False, shard=False, shardsize=100,
                 memcached_json=False, **kw):
        self.sqlstorage = super(MemcachedSQLStorage, self)
        self.sqlstorage.__init__(sqluri,
                                 standard_collections, fixed_collections,
                                 use_quota, quota_size, pool_size,
                                 pool_recycle, create_tables=create_tables,
                                 shard=shard, shardsize=shardsize, **kw)
        if isinstance(cache_servers, str):
            cache_servers = [cache_servers]
        elif cache_servers is None:
            cache_servers = ['127.0.0.1:11211']
        if isinstance(mirrored_cache_servers, str):
            mirrored_cache_servers = [mirrored_cache_servers]
        extra_kw = {}
        if memcached_json:
            extra_kw['pickler'] = _JSONDumper
            extra_kw['unpickler'] = _JSONDumper
        if mirrored_cache_servers is None:
            self.cache = CacheManager(cache_servers, **extra_kw)
        else:
            self.cache = MirroredCacheManager(cache_servers,
                                              mirrored_cache_servers,
                                              **extra_kw)

    @classmethod
    def get_name(self):
        return 'memcached'

    #
    # Cache management
    #
    def _is_meta_global(self, collection_name, item_id):
        return collection_name == 'meta' and item_id == 'global'

    #
    # Cached APIs
    #
    def delete_storage(self, user_id):
        self.cache.flush_user_cache(user_id)
        self.sqlstorage.delete_storage(user_id)

    def delete_user(self, user_id):
        self.cache.flush_user_cache(user_id)
        self.sqlstorage.delete_user(user_id)

    def item_exists(self, user_id, collection_name, item_id):
        """Returns a timestamp if an item exists."""
        def _item_exists():
            return self.sqlstorage.item_exists(user_id, collection_name,
                                               item_id)

        # returning cached values when possible
        if self._is_meta_global(collection_name, item_id):
            key = _key(user_id, 'meta', 'global')
            wbo = self.cache.get(key)
            if wbo is not None:
                return wbo['modified']
            # going sql..

        elif collection_name == 'tabs':
            return self.cache.tab_exists(user_id, item_id)

        return self.sqlstorage.item_exists(user_id, collection_name, item_id)

    def get_items(self, user_id, collection_name, fields=None, filters=None,
                  limit=None, offset=None, sort=None):
        """returns items from a collection

        "filter" is a dict used to add conditions to the db query.
        Its keys are the field names on which the condition operates.
        Its values are the values the field should have.
        It can be a single value, or a list. For the latter the in()
        operator is used. For single values, the operator has to be provided.
        """
        # returning cached values when possible
        if collection_name == 'tabs':
            # tabs are not stored at all in SQL
            return self.cache.get_tabs(user_id, filters).values()

        return self.sqlstorage.get_items(user_id, collection_name,
                                         fields, filters, limit, offset, sort)

    def get_item(self, user_id, collection_name, item_id, fields=None):
        """Returns one item.

        If the item is meta/global, we want to get the cached one if present.
        """
        def _get_item():
            return self.sqlstorage.get_item(user_id, collection_name,
                                            item_id, fields)

        # returning cached values when possible
        if self._is_meta_global(collection_name, item_id):
            key = _key(user_id, 'meta', 'global')
            return self.cache.get_set(key, _get_item)
        elif collection_name == 'tabs':
            # tabs are not stored at all in SQL
            return self.cache.get_tab(user_id, item_id)

        return _get_item()

    def _update_stamp(self, user_id, collection_name, storage_time):
        # update the stamps cache
        if storage_time is None:
            storage_time = round_time()
        stamps = self.get_collection_timestamps(user_id)
        stamps[collection_name] = storage_time
        self.cache.set(_key(user_id, 'stamps'), stamps)

    def _update_cache(self, user_id, collection_name, items, storage_time):
        # update the total size cache (bytes)
        total_size = sum([len(item.get('payload', '')) for item in items])
        self.cache.incr(_key(user_id, 'size'), total_size)

        # update the stamps cache
        self._update_stamp(user_id, collection_name, storage_time)

        # update the meta/global cache or the tabs cache
        if self._is_meta_global(collection_name, items[0]['id']):
            item = items[0]
            item['username'] = user_id
            key = _key(user_id, 'meta', 'global')
            self.cache.set(key, item)
        elif collection_name == 'tabs':
            tabs = dict([(item['id'], item) for item in items])
            self.cache.set_tabs(user_id, tabs)

    def _update_item(self, item, when):
        if 'payload' in item and 'modified' not in item:
            item['modified'] = when

    def set_item(self, user_id, collection_name, item_id, storage_time=None,
                 **values):
        """Adds or update an item"""
        values['id'] = item_id
        if storage_time is None:
            storage_time = round_time()

        self._update_item(values, storage_time)
        self._update_cache(user_id, collection_name, [values], storage_time)

        if collection_name == 'tabs':
            # return now : we don't store tabs in sql
            return storage_time

        return self.sqlstorage.set_item(user_id, collection_name, item_id,
                                        storage_time=storage_time, **values)

    def set_items(self, user_id, collection_name, items, storage_time=None):
        """Adds or update a batch of items.

        Returns a list of success or failures.
        """
        if storage_time is None:
            storage_time = round_time()

        for item in items:
            self._update_item(item, storage_time)

        self._update_cache(user_id, collection_name, items, storage_time)
        if collection_name == 'tabs':
            # return now : we don't store tabs in sql
            return len(items)

        return self.sqlstorage.set_items(user_id, collection_name, items,
                                         storage_time=storage_time)

    def delete_item(self, user_id, collection_name, item_id,
                    storage_time=None):
        """Deletes an item"""
        # Since we don't know how large the item is, we can't make any
        # useful adjustment to the cached size.  Just leave it alone and
        # rely on automatic recalculation to keep it semi-accurate.

        # update the meta/global cache or the tabs cache
        if self._is_meta_global(collection_name, item_id):
            key = _key(user_id, 'meta', 'global')
            self.cache.delete(key)
        elif collection_name == 'tabs':
            # tabs are not stored at all in SQL
            if self.cache.delete_tab(user_id, item_id):
                self._update_stamp(user_id, 'tabs', storage_time)
                return True
            return False

        res = self.sqlstorage.delete_item(user_id, collection_name, item_id)
        if res:
            self._update_stamp(user_id, collection_name, storage_time)
        return res

    def delete_items(self, user_id, collection_name, item_ids=None,
                     filters=None, limit=None, offset=None, sort=None,
                     storage_time=None):
        """Deletes items. All items are removed unless item_ids is provided"""
        # Since we don't know how large the items are, we can't make any
        # useful adjustment to the cached size.  Just leave it alone and
        # rely on automatic recalculation to keep it semi-accurate.

        # remove the cached values
        if (collection_name == 'meta' and (item_ids is None
            or 'global' in item_ids)):
            key = _key(user_id, 'meta', 'global')
            self.cache.delete(key)
        elif collection_name == 'tabs':
            # tabs are not stored at all in SQL
            if self.cache.delete_tabs(user_id, filters):
                self._update_stamp(user_id, 'tabs', storage_time)
                return True
            return False

        res = self.sqlstorage.delete_items(user_id, collection_name,
                                           item_ids, filters,
                                           limit, offset, sort)
        if res:
            self._update_stamp(user_id, collection_name, storage_time)
        return res

    def get_total_size(self, user_id, recalculate=False):
        """Returns the total size in KB of a user storage"""
        def _get_set_size():
            # returns in KB
            size = self.sqlstorage.get_total_size(user_id)

            # adding the tabs
            size += self.cache.get_tabs_size(user_id)

            # update the cache and timestamp
            self.cache.set_total(user_id, size)
            self.cache.set(_key(user_id, "size", "ts"), int(time.time()))
            return size

        # Recalculate from the DB if requested, and if we haven't
        # already done so recently.
        if recalculate:
            last_recalc = self.cache.get(_key(user_id, "size", "ts"))
            if last_recalc is None:
                return _get_set_size()
            if time.time() - last_recalc > QUOTA_RECALCULATION_PERIOD:
                return _get_set_size()

        size = self.cache.get_total(user_id)
        if not size:    # memcached server seems down or needs a reset
            return _get_set_size()

        return size

    def get_size_left(self, user_id, recalculate=False):
        """Returns the storage left for a user"""
        # This gets called to check quota on every write operation,
        # so don't recalculate from the database unless explicitly asked.
        if recalculate:
            size = self.get_total_size(user_id, recalculate)
        else:
            size = self.cache.get_total(user_id)
            if not size:
                size = 0
        return self.quota_size - size

    def get_collection_sizes(self, user_id):
        """Returns the total size in KB for each collection of a user storage.
        """
        # these sizes are not cached
        sizes = self.sqlstorage.get_collection_sizes(user_id)
        sizes['tabs'] = self.cache.get_tabs_size(user_id)

        # we can update the size while we're there, in case it's empty
        self.cache.set_total(user_id, sum(sizes.values()))
        return sizes

    def get_collection_timestamps(self, user_id):
        """Returns a cached version of the stamps when possible"""
        stamps = self.cache.get(_key(user_id, 'stamps'))

        # not cached yet or memcached is down
        if stamps is None:
            stamps = super(MemcachedSQLStorage,
                           self).get_collection_timestamps(user_id)

            # adding the tabs stamp
            tabs_stamps = self.cache.get_tabs_timestamp(user_id)
            if tabs_stamps is not None:
                stamps['tabs'] = tabs_stamps

            # caching it
            self.cache.set(_key(user_id, 'stamps'), stamps)

        return stamps

    def get_collection_max_timestamp(self, user_id, collection_name):
        # let's get them all, so they get cached
        stamps = self.get_collection_timestamps(user_id)
        if collection_name == 'tabs' and 'tabs' not in stamps:
            return None
        return stamps.get(collection_name)
