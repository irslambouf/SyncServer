# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171239.187821
_enable_loop = True
_template_filename = './deps/server-reg/syncreg/templates/password_failure.mako'
_template_uri = 'password_failure.mako'
_source_encoding = 'ascii'
_exports = []


def _mako_get_namespace(context, name):
    try:
        return context.namespaces[(__name__, name)]
    except KeyError:
        _mako_generate_namespaces(context)
        return context.namespaces[(__name__, name)]
def _mako_generate_namespaces(context):
    pass
def _mako_inherit(template, context):
    _mako_generate_namespaces(context)
    return runtime._inherit_from(context, u'base.mako', _template_uri)
def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        error = context.get('error', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'\n\n<div>\nWe were unable to process your request. Please try again later.\n</div>\n\n<div>\nError: ')
        __M_writer(unicode(error))
        __M_writer(u'\n</div>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"33": 1, "34": 8, "27": 0, "35": 8, "41": 35}, "uri": "password_failure.mako", "filename": "./deps/server-reg/syncreg/templates/password_failure.mako"}
__M_END_METADATA
"""
