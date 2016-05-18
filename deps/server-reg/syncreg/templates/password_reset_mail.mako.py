# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.986974
_enable_loop = True
_template_filename = './deps/server-reg/syncreg/templates/password_reset_mail.mako'
_template_uri = 'password_reset_mail.mako'
_source_encoding = 'ascii'
_exports = []


def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        url = context.get('url', UNDEFINED)
        host = context.get('host', UNDEFINED)
        code = context.get('code', UNDEFINED)
        user_name = context.get('user_name', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'You asked to reset your Weave password. To do so, please click this link:\n\n    ')
        __M_writer(unicode(host))
        __M_writer(unicode(url))
        __M_writer(u'?username=')
        __M_writer(unicode(user_name))
        __M_writer(u'&key=')
        __M_writer(unicode(code))
        __M_writer(u"\n\n\nThis will let you change your password to something new. If you didn't ask for this, don't worry, we'll keep your password safe.\n\n\nBest Wishes\nThe Weave Team\n")
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"32": 3, "38": 32, "16": 0, "25": 1, "26": 3, "27": 3, "28": 3, "29": 3, "30": 3, "31": 3}, "uri": "password_reset_mail.mako", "filename": "./deps/server-reg/syncreg/templates/password_reset_mail.mako"}
__M_END_METADATA
"""
