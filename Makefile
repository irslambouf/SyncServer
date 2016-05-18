DEPS = server-core,server-reg,server-storage,server-key-exchange
PYTHON = `which python2 python | head -n 1`
VIRTUALENV = virtualenv --python=$(PYTHON)
NOSE = bin/nosetests -s --with-xunit
TESTS = deps/server-core/services/tests deps/server-reg/syncreg/tests deps/server-storage/syncstorage/tests deps/server-key-exchange/keyexchange/tests
BUILDAPP = bin/buildapp
BUILDRPMS = bin/buildrpms
SCHEME = https
PYPI = $(SCHEME)://pypi.python.org/simple
PYPIOPTIONS = -i $(PYPI)
CHANNEL = dev
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
	INSTALLOPTIONS += --install-option="--allow-hosts=$(HOST)"

endif

INSTALL += $(INSTALLOPTIONS)


.PHONY: all build update test build_rpms


all:	build

build:
	$(VIRTUALENV) --distribute --no-site-packages .
	$(INSTALL) pip
	$(INSTALL) Distribute
	$(INSTALL) MoPyTools
	$(INSTALL) Nose
	$(INSTALL) WebTest
	# Build these first because it seems to fail out on some people's
	# machines but then recover on subsequent build.
	$(INSTALL) -r dev-reqs.txt
	$(BUILDAPP) -c $(CHANNEL) $(PYPIOPTIONS) $(DEPS)
	./bin/python setup.py develop
	# Pre-compile mako templates into the correct directories.
	for TMPL in `find . -name '*.mako'`; do ./bin/python -c "from mako.template import Template; Template(filename='$$TMPL', module_directory='`dirname $$TMPL`', uri='`basename $$TMPL`')"; done;

update:
	$(BUILDAPP) -c $(CHANNEL) $(PYPIOPTIONS) $(DEPS)
	# Pre-compile mako templates into the correct directories.
	for TMPL in `find . -name '*.mako'`; do ./bin/python -c "from mako.template import Template; Template(filename='$$TMPL', module_directory='`dirname $$TMPL`', uri='`basename $$TMPL`')"; done;

test:
	$(NOSE) $(TESTS)

build_rpms:
	$(BUILDRPMS) -c $(CHANNEL) $(DEPS)
