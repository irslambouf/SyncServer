# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171239.276669
_enable_loop = True
_template_filename = './deps/server-reg/syncreg/templates/password_ask_reset_form.mako'
_template_uri = 'password_ask_reset_form.mako'
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
        url = context.get('url', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'\n\n<p>Enter your username here and we\'ll send you an email with instructions and a key that will let you reset your password.</p>\n\n<div class="box">\n <form class="mainForm" name="forgotPass" id="forgotPass"\n       action="')
        __M_writer(unicode(url))
        __M_writer(u'" method="post">\n  <p>\n   <label>Username:<br />\n   <input type="text" name="username" id="user_login" size="20" /></label>\n  </p>\n  <p class="submit">\n    <input type="submit" id="fpsubmit" value="Request Reset Key" />\n  </p>\n  <p>&nbsp;</p>\n </form>\n</div>\n\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"33": 1, "34": 7, "27": 0, "35": 7, "41": 35}, "uri": "password_ask_reset_form.mako", "filename": "./deps/server-reg/syncreg/templates/password_ask_reset_form.mako"}
__M_END_METADATA
"""
