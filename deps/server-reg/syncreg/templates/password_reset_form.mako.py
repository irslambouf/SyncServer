# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.620693
_enable_loop = True
_template_filename = './deps/server-reg/syncreg/templates/password_reset_form.mako'
_template_uri = 'password_reset_form.mako'
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
        username = context.get('username', UNDEFINED)
        key = context.get('key', UNDEFINED)
        error = context.get('error', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u"\n<p>\n <strong>Note:</strong> Do not set this to be the same as your\n passphrase! If you are unsure what your passphrase is, you'll need\n to trigger a server wipe from the Weave add-on.</p>\n\n")
        if error:
            __M_writer(u' <div class="error">')
            __M_writer(unicode(error))
            __M_writer(u'</div>\n')
        __M_writer(u' <form class="mainForm" name="changePass" id="changePass"\n    action="')
        __M_writer(unicode(url))
        __M_writer(u'" method="post">\n  <p>\n   <label>New password:\n    <input type="password" name="password" id="user_pass" size="20"/>\n   </label>\n  </p>\n  <p>\n   <label>Re-enter to confirm:\n    <input type="password" name="confirm"\n           id="user_pass2" size="20"/>\n   </label>\n  </p>\n  <input type="hidden" name="key" value="')
        __M_writer(unicode(key))
        __M_writer(u'"/>\n')
        if username:
            __M_writer(u'  <input type="hidden" name="username" value="')
            __M_writer(unicode(username))
            __M_writer(u'"/>\n')
        __M_writer(u'  <input type="submit" id="pchange" name="pchange"\n         value="Change my password"/>\n </form>\n</p>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"36": 1, "37": 7, "38": 8, "39": 8, "40": 8, "41": 10, "42": 11, "43": 11, "44": 23, "45": 23, "46": 24, "47": 25, "48": 25, "49": 25, "50": 27, "56": 50, "27": 0}, "uri": "password_reset_form.mako", "filename": "./deps/server-reg/syncreg/templates/password_reset_form.mako"}
__M_END_METADATA
"""
