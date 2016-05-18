APPNAME = server-core
DEPS =
VIRTUALENV = virtualenv
PYTHON = bin/python
NOSE = bin/nosetests -s --with-xunit
FLAKE8 = bin/flake8
COVEROPTS = --cover-html --cover-html-dir=html --with-coverage --cover-package=services
TESTS = services
PKGS = services
COVERAGE = bin/coverage
PYLINT = bin/pylint
SERVER = dev-auth.services.mozilla.com
SCHEME = https
BUILDAPP = bin/buildapp
BUILDRPMS = bin/buildrpms
PYPI = http://pypi.python.org/simple
PYPI2RPM = bin/pypi2rpm.py --index=$(PYPI)
PYPIOPTIONS = -i $(PYPI)
CHANNEL = dev
RPM_CHANNEL = prod
INSTALL = bin/pip install
INSTALLOPTIONS = -U -i $(PYPI)

ifdef PYPIEXTRAS
	PYPIOPTIONS += -e $(PYPIEXTRAS)
	INSTALLOPTIONS += -f $(PYPIEXTRAS)
endif

ifdef PYPISTRICT
	PYPIOPTIONS += -s
	ifdef PYPIEXTRAS
		HOST = `python -c "import urlparse; print urlparse.urlparse('$(PYPI)')[1] + ',' + urlparse.urlparse('$(PYPIEXTRAS)')[1]"`

	else
		HOST = `python -c "import urlparse; print urlparse.urlparse('$(PYPI)')[1]"`
	endif

endif

INSTALL += $(INSTALLOPTIONS)

.PHONY: all build build_extras build_rpms test update

all:	build

build:
	$(VIRTUALENV) --no-site-packages --distribute .
	$(INSTALL) Distribute
	$(INSTALL) MoPyTools
	$(INSTALL) nose
	$(INSTALL) WebTest
	$(INSTALL) wsgi_intercept
	$(BUILDAPP) -c $(CHANNEL) $(PYPIOPTIONS) $(DEPS)

update:
	$(BUILDAPP) -c $(CHANNEL) $(PYPIOPTIONS) $(DEPS)

build_extras:
	$(INSTALL) MySQL-python
	$(INSTALL) recaptcha-client
	$(INSTALL) wsgiproxy
	$(INSTALL) wsgi_intercept
	$(INSTALL) "python-ldap == 2.3.13"
	$(INSTALL) coverage
	$(INSTALL) Pygments

test:
	$(NOSE) $(TESTS)

build_rpms:
	$(BUILDRPMS) -c $(RPM_CHANNEL) $(DEPS)
