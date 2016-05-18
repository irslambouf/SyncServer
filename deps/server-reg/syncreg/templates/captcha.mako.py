# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.802942
_enable_loop = True
_template_filename = './deps/server-reg/syncreg/templates/captcha.mako'
_template_uri = 'captcha.mako'
_source_encoding = 'ascii'
_exports = []


def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        captcha = context.get('captcha', UNDEFINED)
        error = context.get('error', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'<body>\n   <div id="content">\n')
        if error:
            __M_writer(u'    <strong>Wrong answer</strong>\n')
        __M_writer(u'\n   <script>var RecaptchaOptions = {theme: "clean"};\n   </script>\n   <div style="background-color: system;">\n    <form action="/misc/1.0/captcha_html" method="POST" >\n      ')
        __M_writer(unicode(captcha))
        __M_writer(u'\n    </form>\n   </div>\n  </div>\n</body>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"34": 28, "16": 0, "23": 1, "24": 3, "25": 4, "26": 6, "27": 11, "28": 11}, "uri": "captcha.mako", "filename": "./deps/server-reg/syncreg/templates/captcha.mako"}
__M_END_METADATA
"""
