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
""" Configuration file reader / writer

https://wiki.mozilla.org/index.php?title=Services/Sync/Server/GlobalConfFile
"""
import re
import os
from copy import copy
from ConfigParser import RawConfigParser
from services.exceptions import EnvironmentNotFoundError


_IS_NUMBER = re.compile('^-?[0-9].*')
_IS_ENV_VAR = re.compile('\$\{(\w.*)?\}')


def convert(value):
    """Converts a config value"""
    def _get_env(matchobj):
        var = matchobj.groups()[0]
        if var not in os.environ:
            raise EnvironmentNotFoundError(var)
        return os.environ[var]

    def _convert(value):
        if not isinstance(value, basestring):
            # already converted
            return value

        value = value.strip()
        if _IS_NUMBER.match(value):
            try:
                return int(value)
            except ValueError:
                pass
        elif value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        elif value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        return _IS_ENV_VAR.sub(_get_env, value)

    if isinstance(value, basestring) and '\n' in value:
        return [line for line in [_convert(line)
                                  for line in value.split('\n')]
                if line != '']

    return _convert(value)


class SvcConfigParser(RawConfigParser):

    def __init__(self, filename):
        # let's read the file
        RawConfigParser.__init__(self)
        if isinstance(filename, basestring):
            self.read(filename)
        else:
            self.readfp(filename)

    def _read(self, fp, filename):
        # first pass
        RawConfigParser._read(self, fp, filename)

        # let's expand it now if needed
        defaults = self.defaults()

        if'extends' in defaults:
            extends = defaults['extends']
            if not isinstance(extends, list):
                extends = [extends]
            for file_ in extends:
                self._extend(file_)

    def _serialize(self, value):
        """values are serialized on every set"""
        if isinstance(value, bool):
            value = str(value).lower()
        elif isinstance(value, (int, long)):
            value = str(value)
        elif isinstance(value, (list, tuple)):
            value = '\n'.join(['    %s' % line for line in value]).strip()
        else:
            value = str(value)
        return value

    def _unserialize(self, value):
        """values are serialized on every get"""
        return convert(value)

    def get_map(self, section=None):
        """returns a dict representing the config set"""
        if section:
            return dict(self.items(section))

        res = {}
        for section in self.sections():
            for option, value in self.items(section):
                option = '%s.%s' % (section, option)
                res[option] = self._unserialize(value)
        return res

    def set(self, section, option, value):
        value = self._serialize(value)
        RawConfigParser.set(self, section, option, value)

    def mget(self, section, option):
        value = self.get(section, option)
        if not isinstance(value, list):
            value = [value]
        return value

    def get(self, section, option):
        value = RawConfigParser.get(self, section, option)
        return self._unserialize(value)

    def items(self, section):
        items = RawConfigParser.items(self, section)
        return [(option, self._unserialize(value)) for option, value in items]

    def _extend(self, filename):
        """Expand the config with another file."""
        if not os.path.isfile(filename):
            raise IOError('No such file: %s' % filename)
        parser = RawConfigParser()
        parser.read([filename])
        for section in parser.sections():
            if not self.has_section(section):
                self.add_section(section)
            for option, value in parser.items(section):
                if self.has_option(section, option):
                    continue
                RawConfigParser.set(self, section, option, value)


class Config(dict):
    """
    Base class which encapsulates all functionality related to the loading of
    services app config.  It can be used by itself if it is passed an
    application config dictionary, or subclasses can be provided which know how
    to extract app config info from other formats or contexts.
    """
    splitchar = '.'

    def __init__(self, cfgdict=None, cfgfile=None):
        if cfgdict is not None:
            self.load_config(cfgdict)
        if cfgfile is not None:
            self.load_from_file(cfgfile)
        self._merge_cache = dict()

    def load_config(self, cfgdict):
        """
        Loads the provided configuration, performing any necessary conversions,
        into the stored config.  Will overwrite any previously stored config
        settings if a value is provided for an already stored key.

        Any config value starting w/ 'file:' will not be loaded directly into
        the stored config.  Instead, the specified file path will be
        dereferenced and the resulting file will be passed to the
        `load_from_file` method.

        (assumed to be another config file)
        will be loaded using SvcConfigParser.  Each section/option of the
        loaded file will be converted to 'section.option' in the resulting
        mapping.
        """
        for key, value in cfgdict.items():
            if (not isinstance(value, basestring)
                or not value.startswith('file:')):
                self[key] = convert(value)
                continue

            path = value[len('file:'):]
            self.load_from_file(path)

    def load_from_file(self, path):
        """
        Uses SvcConfigParser to load configuration info from the specified
        file.  Keys will be added to the config dictionary as
        '<section>.<key>'.
        """
        if not os.path.exists(path):
            raise ValueError('The configuration file was not found. "%s"' %
                             path)
        conf = SvcConfigParser(path)
        here_path = os.path.dirname(path)
        for key, value in conf.get_map().iteritems():
            if isinstance(value, basestring):
                value = value.replace("%(here)s", here_path)
            self[key] = value

    def get_section(self, section):
        """
        Returns a dictionary containing only the config for the specified
        section, removing the '<section>.' prefix from all of the key names.
        If the section value is the empty string we return any values that have
        no section prefix.

        Returns an empty dict for sections that don't exist.
        """
        sec_cfg = dict()
        default = section == ''
        for key, value in self.items():
            if self.splitchar not in key and not default:
                continue
            skey = key
            if self.splitchar in skey:
                if not skey.startswith(section + self.splitchar):
                    continue
                skey = skey[len(section + self.splitchar):]
            sec_cfg[skey] = value
        return sec_cfg

    def merge(self, *sections):
        """
        Merge settings from the specified sections into other sections as
        determined by the splitchar prefix in the specified sections.
        """
        if sections in self._merge_cache:
            return self._merge_cache[sections]
        ret = copy(self)
        for section in sections:
            section_map = self.get_section(section)
            for k, v in section_map.items():
                if self.splitchar not in k:
                    continue
                ret[k] = v
        self._merge_cache[sections] = ret
        return ret

    def clear_merge_cache(self):
        self._merge_cache = dict()
