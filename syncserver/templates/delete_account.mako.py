# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.415688
_enable_loop = True
_template_filename = './syncserver/templates/delete_account.mako'
_template_uri = 'delete_account.mako'
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
        __M_writer(u'\n<p>\n To permanently delete your Firefox Sync account and all copies of your data stored on our servers, please enter your username and password and click Permanently Delete My Account.\n</p>\n')
        if error:
            __M_writer(u' <div class="error">')
            __M_writer(unicode(error))
            __M_writer(u'</div>\n')
        __M_writer(u' <form class="mainForm" name="deleteAccount" id="deleteAccount"\n    action="/weave-delete-account" method="post">\n  <p>\n  <label>Username:\n    <input type="text" name="username" id="user_name" size="20"/>\n   </label>\n  </p>\n  <label>Password:\n    <input type="password" name="password" id="user_pass" size="20"/>\n   </label>\n  </p>\n\n  <input type="submit" id="pchange" name="pchange"\n         value="Permanently Delete My Account"/>\n </form>\n</p>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"33": 1, "34": 5, "35": 6, "36": 6, "37": 6, "38": 8, "44": 38, "27": 0}, "uri": "delete_account.mako", "filename": "./syncserver/templates/delete_account.mako"}
__M_END_METADATA
"""
