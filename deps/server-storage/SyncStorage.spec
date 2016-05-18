%define name python26-syncstorage
%define pythonname SyncStorage
%define version 1.18
%define release 2

Summary: Sync Storage server
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{pythonname}-%{version}.tar.gz
License: MPL
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{pythonname}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Tarek Ziade <tarek@mozilla.com>
BuildRequires: libevent-devel libmemcached-devel
Requires: nginx memcached gunicorn logstash-metlog >= 0.8.3 python26 python26-pylibmc python26-setuptools python26-webob python26-paste python26-pastedeploy python26-services >= 1.0 python26-pastescript python26-sqlalchemy python26-simplejson python26-cef python26-gevent python26-pymysql python26-pymysql_sa python26-greenlet python26-metlog-py python26-meliae
Conflicts: python26-syncreg
Url: https://hg.mozilla.org/services/server-storage

%description
============
Sync Storage
============

This is the Python implementation of the Storage Server.


%prep
%setup -n %{pythonname}-%{version} -n %{pythonname}-%{version}

%build
python2.6 setup.py build

%install

# the config files for Sync apps
mkdir -p %{buildroot}%{_sysconfdir}/sync
install -m 0644 etc/sync.conf %{buildroot}%{_sysconfdir}/sync/sync.conf
install -m 0644 etc/production.ini %{buildroot}%{_sysconfdir}/sync/production.ini

# nginx config
mkdir -p %{buildroot}%{_sysconfdir}/nginx
mkdir -p %{buildroot}%{_sysconfdir}/nginx/conf.d
install -m 0644 etc/syncstorage.nginx.conf %{buildroot}%{_sysconfdir}/nginx/conf.d/syncstorage.conf

# logging
mkdir -p %{buildroot}%{_localstatedir}/log
touch %{buildroot}%{_localstatedir}/log/syncstorage.log

# the app
python2.6 setup.py install --single-version-externally-managed --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES

# This works around a problem with rpmbuild, where it pre-gnerates .pyo
# files that aren't included in the INSTALLED_FILES list by bdist_rpm.
for PYO_FILE in `cat INSTALLED_FILES | grep '.pyc$' | sed 's/.pyc$/.pyo/'`; do
  if [ -f $PYO_FILE ]; then
    echo $PYO_FILE >> INSTALLED_FILES
  fi;
done;

%clean
rm -rf $RPM_BUILD_ROOT

%post
touch %{_localstatedir}/log/syncstorage.log
chown nginx:nginx %{_localstatedir}/log/syncstorage.log
chmod 640 %{_localstatedir}/log/syncstorage.log

%files -f INSTALLED_FILES

%attr(640, nginx, nginx) %ghost %{_localstatedir}/log/syncstorage.log

%dir %{_sysconfdir}/sync/

%config(noreplace) %{_sysconfdir}/sync/sync.conf
%config(noreplace) %{_sysconfdir}/sync/production.ini
%config(noreplace) %{_sysconfdir}/nginx/conf.d/syncstorage.conf

%defattr(-,root,root)
