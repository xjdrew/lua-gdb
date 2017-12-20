from __future__ import print_function
import re
import sys

print("Loading Lua Runtime support.", file=sys.stderr)
#http://python3porting.com/differences.html
if sys.version > '3':
    xrange = range

# allow to manually reload while developing
objfile = gdb.current_objfile() or gdb.objfiles()[0]
objfile.pretty_printers = []

# input GCObject*
def cast_u(o):
    tt = gdb.lookup_type("union GCUnion")
    return o.cast(tt.pointer())

# <TValue> -> <int>
def ivalue(o): return o['value_']['i']

# <TValue> -> <float>
def fltvalue(o): return o['value_']['n']

# <TValue> -> <lightuserdata>
def pvalue(o): return o['value_']['p']

# <TValue> -> <TString>
def tsvalue(o): return cast_u(o['value_']['gc'])['ts']

# <TValue> -> <LClosure>
def clLvalue(o): return cast_u(o['value_']['gc'])['cl']['l']

# <TValue> -> <CClosure>
def clCvalue(o): return cast_u(o['value_']['gc'])['cl']['c']

# <TValue> -> <lua_CFunction>
def fvalue(o): return o['value_']['f']

# <TValue> -> <Table>
def hvalue(o): return cast_u(o['value_']['gc'])['h']

# <TValue> -> <boolean>
def bvalue(o): return o['value_']['b']

# test type
def ttisnumber(o): return o['tt_']&0xf == 3
def ttisfloat(o): return o['tt_'] == 3
def ttisinteger(o): return o['tt_'] == 3 | (1<<4)
def ttisnil(o): return o['tt_'] == 0
def ttisboolean(o): return o['tt_'] == 1
def ttislightuserdata(o): return o['tt_'] == 2
def ttisstring(o): return o['tt_']&0xf == 4
def ttisshrstring(o): return o['tt_']&0xf == 4
def ttislngstring(o): return o['tt_'] == 0x40 | 4 
def ttislngstring(o): return o['tt_'] == 0x40 | 4 | (1<<4)
def ttistable(o): return o['tt_'] == 0x40 | 5
def ttisfunction(o): return o['tt_']&0xf == 6
def ttisclosure(o): return o['tt_']&0x1f == 6
def ttisCclosure(o): return o['tt_'] == 0x40 | 6 | (2<<4)
def ttisLclosure(o): return o['tt_'] == 0x40 | 6 | (0<<4)
def ttislcf(o): return o['tt_'] == 6 | (1<<4)
def ttisfulluserdata(o): return o['tt_'] == 0x40 | 7
def ttisthread(o): return o['tt_'] == 0x40 | 8

#
# Value wrappers
#

class CallInfoValue:
    "Wrapper for CallInfo value."

    CIST_LUA = 1<<1
    CIST_TAIL = 1<<5
    CIST_FIN = 1<<8

    def __init__(self, val):
        self.val = val

        if ttisLclosure(self.val['func']):
            proto = clLvalue(self.val['func'])['p']

            if not proto['source']:
                self.source = "=?"
            else:
                self.source = proto['source'].dereference()

            self.linedefined = proto['linedefined']
            self.lastlinedefined = proto['lastlinedefined']

            if self.linedefined == 0:
                self.what = "main"
            else:
                self.what = "Lua"

            if proto['lineinfo']:
                currentpc = (self.val['u']['l']['savedpc'] - proto['code']) - 1 
                self.currentline = (proto['lineinfo']+currentpc).dereference()
            else:
                self.currentline = -1
        else:
            self.source = "=[C]"
            self.linedefined = -1
            self.lastlinedefined = -1
            self.what = "C"
            self.currentline = -1

        self.name = None
        self.namewhat = None

        if self.is_fin():
            self.name = "__gc"
            self.namewhat = "metamethod"

    @property
    def funcname(self):
        if self.what == "main":
            return "main chunk"
        elif self.namewhat:
            return "%s '%s'" % (self.namewhat, self.name)
        return '?'

    def is_lua(self):
        return self.val['callstatus'] & CallInfoValue.CIST_LUA

    def is_tailcall(self):
        return self.val['callstatus'] & CallInfoValue.CIST_TAIL

    def is_fin(self):
        return self.val['callstatus'] & CallInfoValue.CIST_FIN

#
# Pretty Printers
#

class TValuePrinter:
    "Pretty print lua value."

    pattern = re.compile(r'^(struct TValue)|(TValue)$')

    def __init__(self, val):
        self.val = val

    def to_string(self):
        if ttisnil(self.val): # nil
            return "nil"
        elif ttisboolean(self.val): # boolean
            return bvalue(self.val) > 0
        elif ttislightuserdata(self.val): # lightuserdata
            return "<lightuserdata 0x%x>" % int(pvalue(self.val))
        elif ttisnumber(self.val): # number
            if ttisfloat(self.val):
                return nvalue(self.val)
            elif ttisinteger(self.val):
                return ivalue(self.val)
        elif ttisstring(self.val): # string
            return tsvalue(self.val)
        elif ttistable(self.val): # table
            return hvalue(self.val)
        elif ttisfunction(self.val):
            if ttisLclosure(self.val): # lua closure
                return clLvalue(self.val)
            elif ttislcf(self.val): # light C function
                return fvalue(self.val)
            elif ttisCclosure(self.val): # 2 C closure
                return clCvalue(self.val)
        elif ttisfulluserdata(self.val):
            return "Userdata"
        elif ttisthread(self.val):
            return "Thread"
        assert False, self.val['tt_']

    def display_hint(self):
        return "string"

class TStringPrinter:
    "Pretty print lua string."

    pattern =  re.compile(r'^(struct TString)|(TString)$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "string"

    def to_string(self):
        s = self.val.address + 1
        return s.cast(gdb.lookup_type('char').pointer())

class TablePrinter:
    "Pretty print lua table."

    pattern =  re.compile(r'^(struct Table)|(Table)$')
    marked = None

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "map"

    def to_string(self):
        return "<table 0x%x>" % int(self.val.address)

    def children(self):
        setMarked = False
        if TablePrinter.marked == None:
            TablePrinter.marked = {}
            setMarked = True

        address = int(self.val.address)
        if address in TablePrinter.marked:
            return TablePrinter.marked[address]
        TablePrinter.marked[address] = self.to_string()

        # array part
        i = 0
        while i < self.val['sizearray']:
            val = self.val['array'] + i
            i = i + 1
            yield str(2*i), i
            yield str(2*i + 1), val.dereference()

        # hash part
        j = 0
        last = 1 << self.val['lsizenode']
        while j < last:
            node = self.val['node'] + j
            j = j + 1
            key = node['i_key']['tvk']
            if ttisnil(key): 
                continue
            yield str(2*i + 2*j), key
            yield str(2*i + 2*j + 1), node['i_val']

        if setMarked:
            TablePrinter.marked = None

class LClosurePrinter:
    "Pretty print lua closure."

    pattern = re.compile(r'^(struct LClosure)|(LClosure)$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "map"

    def to_string(self):
        p = self.val['p']
        return "<lclosure 0x%x>" % int(self.val.address)

    def children(self):
        p = self.val['p']
        yield "1", "file"
        yield "2", p['source'].dereference()
        yield "3", "linestart"
        yield "4", p['linedefined']
        yield "5", "lineend"
        yield "6", p['lastlinedefined']
        yield "7", "nupvalues"
        yield "8", self.val['nupvalues']

class CClosurePrinter:
    "Pretty print lua closure."

    pattern = re.compile(r'^(struct CClosure)|(CClosure)$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "map"

    def to_string(self):
        p = self.val['p']
        return "<cclosure 0x%x>" % int(self.val.address)

    def children(self):
        yield "1", "nupvalues"
        yield "2", self.val['nupvalues']
#
#    Register all the *Printer classes above.
#

def makematcher(klass):
    def matcher(val):
        try:
            if klass.pattern.match(str(val.type)):
                return klass(val)
        except Exception:
            pass
    return matcher

objfile.pretty_printers.extend([makematcher(var) for var in vars().values() if hasattr(var, 'pattern')])

class LuaStackFunc(gdb.Function):
    def __init__(self):
        gdb.Function.__init__(self, "luastack")

    def invoke(self):
        return "lua stacK"

class LuaStackCmd(gdb.Command):
    """luastack [L]
Prints values on the Lua C stack. Without arguments, uses the current value of "L"
as the lua_State*. You can provide an alternate lua_State as the first argument."""

    def __init__(self):
        gdb.Command.__init__(self, "luastack", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty):
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = gdb.parse_and_eval(argv[0])
        else:
            L = gdb.parse_and_eval("L")

        stack = L['top'] - 1
        while stack >= L['stack']:
            print(stack.dereference())
            stack = stack - 1

class LuaBacktrace(gdb.Command):
    """luabacktrace [L]
Dumps Lua execution stack, as debug.traceback() does. Without
arguments, uses the current value of "L" as the
lua_State*. You can provide an alternate lua_State as the
first argument.
    """
    def __init__(self):
        gdb.Command.__init__(self, "luabacktrace", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty): 
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = gdb.parse_and_eval(argv[0])
        else:
            L = gdb.parse_and_eval("L")

        ci = L['ci']
        print("stack traceback:")
        while ci != L['base_ci'].address:
            cv = CallInfoValue(ci)
            print('\t%s:%d: in %s' % (cv.source, cv.currentline, cv.funcname))
            if cv.is_tailcall():
                print('\t(...tail calls...)')
            ci = ci['previous']

LuaStackFunc()
LuaStackCmd()
LuaBacktrace()
