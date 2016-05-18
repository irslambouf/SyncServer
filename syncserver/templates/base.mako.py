# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.324001
_enable_loop = True
_template_filename = './syncserver/templates/base.mako'
_template_uri = 'base.mako'
_source_encoding = 'ascii'
_exports = []


def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        self = context.get('self', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">\n<html xmlns="http://www.w3.org/1999/xhtml" dir="ltr" lang="en">\n<head>\n  <title>Mozilla Labs / Weave / Forgot Password</title>\n    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />\n    <link rel=\'stylesheet\' href=\'/media/forgot_password.css\' type=\'text/css\' media=\'all\' />\n</head>\n<body>\n  <div id="content">\n    <div id="top">\n      <img src="/media/weave-logo.png" alt="Weave for Firefox" />\n    </div>\n    <div id="bottom">\n      <div><img src="/media/table-top.png" alt="" /></div>\n\n      <div class="table_middle">\n        <div class="title">Password Reset</div>\n        <div class="details">\n          ')
        __M_writer(unicode(self.body()))
        __M_writer(u'\n        </div>\n      </div>\n    <div id="footer">\n      <div class="legal">\n        &copy; 2010 Mozilla\n        <br />\n        <span>\n          <a href="http://www.mozilla.com/en-US/about/legal.html">Legal Notices</a> |\n          <a href="http://www.mozilla.com/en-US/privacy-policy.html">Privacy Policy</a>\n        </span>\n      </div>\n    </div>\n  </div>\n</body>\n</html>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"16": 0, "24": 19, "30": 24, "22": 1, "23": 19}, "uri": "base.mako", "filename": "./syncserver/templates/base.mako"}
__M_END_METADATA
"""
