# -*- coding:ascii -*-
from mako import runtime, filters, cache
UNDEFINED = runtime.UNDEFINED
STOP_RENDERING = runtime.STOP_RENDERING
__M_dict_builtin = dict
__M_locals_builtin = locals
_magic_number = 10
_modified_time = 1463171238.526139
_enable_loop = True
_template_filename = './deps/server-key-exchange/keyexchange/filtering/admin.mako'
_template_uri = 'admin.mako'
_source_encoding = 'ascii'
_exports = []


def render_body(context,**pageargs):
    __M_caller = context.caller_stack._push_frame()
    try:
        __M_locals = __M_dict_builtin(pageargs=pageargs)
        ips = context.get('ips', UNDEFINED)
        observe = context.get('observe', UNDEFINED)
        admin_page = context.get('admin_page', UNDEFINED)
        __M_writer = context.writer()
        __M_writer(u'<html>\n <body>\n   <h1>\n')
        if not observe:
            __M_writer(u'    Status: Active\n')
        if observe:
            __M_writer(u'    Status: Observing\n')
        __M_writer(u'   </h1>\n   <h2>Blacklisted IPs</h2>\n')
        if not ips:
            __M_writer(u'   None\n')
        if ips:
            __M_writer(u'   <form action="')
            __M_writer(unicode(admin_page))
            __M_writer(u'" method="POST">\n    <table border="1">\n     <tr>\n       <th>IP</th>\n       <th>Remove from blacklist</th>\n     </tr>\n')
            for ip in ips:
                __M_writer(u'     <tr>\n      <td>')
                __M_writer(unicode(ip))
                __M_writer(u'</td> \n      <td><input type="checkbox" name="')
                __M_writer(unicode(ip))
                __M_writer(u'"></input></td>\n     </tr>\n')
            __M_writer(u'    </table>\n    <input type="submit"></input>\n   </form>\n')
        __M_writer(u' </body>\n</html>\n')
        return ''
    finally:
        context.caller_stack._pop_frame()


"""
__M_BEGIN_METADATA
{"source_encoding": "ascii", "line_map": {"16": 0, "24": 1, "25": 4, "26": 5, "27": 7, "28": 8, "29": 10, "30": 12, "31": 13, "32": 15, "33": 16, "34": 16, "35": 16, "36": 22, "37": 23, "38": 24, "39": 24, "40": 25, "41": 25, "42": 28, "43": 32, "49": 43}, "uri": "admin.mako", "filename": "./deps/server-key-exchange/keyexchange/filtering/admin.mako"}
__M_END_METADATA
"""
