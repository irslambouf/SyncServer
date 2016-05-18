

class NullObject(object):
    """
    Null Object used when the logging client is completely disabled
    """
    # TODO: this is useful in services.tests.support, but it feels
    # wrong to put it in there and import test suport code into
    # production
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, key):
        return self

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, value):
        return self

    def __delitem__(self, key, value):
        return self

    def __setattr__(self, key, value):
        return self

    def __len__(self):
        return 0

    def __getslice__(self, i, j):
        return self

    def __setslice__(self, i, j, seq):
        return self

    def __delslice__(self, i, j):
        return self

    def __contains__(self, item):
        return False

    def __delattr__(self, key):
        return self

    def __unicode__(self):
        return u"<NullObject>"

    def __repr__(self):
        return str(unicode(self))

    def __call__(self, *args, **kwargs):
        return self

    # Empty iterator
    def __iter__(self):
        return self

    def next(self):
        raise StopIteration
