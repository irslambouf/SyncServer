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
Application entry point.
"""
from services.baseapp import set_app
from services.wsgiauth import Authentication
from syncserver.controllers import MainController

# XXX alternatively we should use Paste composite feature here
from syncreg.wsgiapp import urls as reg_urls, controllers as reg_controllers
from syncstorage.wsgiapp import (StorageServerApp,
                                 controllers as storage_controllers,
                                 urls as storage_urls)


urls = [('GET', '/weave-delete-account', 'main', 'delete_account_form'),
        ('POST', '/weave-delete-account', 'main', 'do_delete_account')]

urls = urls + reg_urls + storage_urls
reg_controllers.update(storage_controllers)
reg_controllers['main'] = MainController

make_app = set_app(urls, reg_controllers, klass=StorageServerApp,
                   auth_class=Authentication)
