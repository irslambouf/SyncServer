%define name python26-services
%define pythonname Services
%define version 2.16
%define unmangled_version %{version}
%define release 2

Summary: Services core tools
Name: %{name}
Version: %{version}
Release: %{release}
Source0: %{pythonname}-%{unmangled_version}.tar.gz
License: MPL
Group: Development/Libraries
BuildRoot: %{_tmppath}/%{pythonname}-%{version}-%{release}-buildroot
Prefix: %{_prefix}
BuildArch: noarch
Vendor: Tarek Ziade <tarek@mozilla.com>
Requires: nginx memcached gunicorn openldap-devel python26 python26-memcached python26-setuptools python26-webob python26-paste python26-pastedeploy python26-sqlalchemy python26-simplejson python26-routes python26-ldap python26-pymysql python26-pymysql_sa python26-cef
Obsoletes: python26-synccore

Url: https://hg.mozilla.org/services/server-core

%description
========
Services
========

Core library that provides these features:

- CEF logger
- Config reader/writer
- Plugin system
- Base WSGI application for Services servers
- Error codes for Sync
- Authentication back ends for Services
- Captcha wrappers


%prep
%setup -n %{pythonname}-%{unmangled_version} -n %{pythonname}-%{unmangled_version}

%build
python2.6 setup.py build

%install
python2.6 setup.py install --single-version-externally-managed --root=$RPM_BUILD_ROOT --record=INSTALLED_FILES
# This works around a problem with rpmbuild, where it pre-generates .pyo
# files that aren't included in the INSTALLED_FILES list by bdist_rpm.
for PYO_FILE in `cat INSTALLED_FILES | grep '.pyc$' | sed 's/.pyc$/.pyo/'`; do
  if [ -f $PYO_FILE ]; then
    echo $PYO_FILE >> INSTALLED_FILES
  fi;
done;

%clean
rm -rf $RPM_BUILD_ROOT

%files -f INSTALLED_FILES

%defattr(-,root,root)
