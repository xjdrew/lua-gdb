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

def cast_u(o):
    tt = gdb.lookup_type("union GCUnion")
    return o.cast(tt.pointer())

def ttisnil(o):
    return o['tt_'] == 0

#
# Pretty Printers
#

class TValuePrinter:
    "Pretty print lua value."

    pattern = re.compile(r'^(struct TValue)|(TValue)$')

    def __init__(self, val):
        self.val = val

    def to_string(self):
        val = self.val['value_']
        mtt = self.val['tt_']&0xf
        stt = (self.val['tt_']>>4)&0x3

        if mtt == 0: # nil
            return "nil"
        elif mtt == 1: # boolean
            return val['b'] > 0
        elif mtt == 2: # lightuserdata
            return "<lightuserdata 0x%x>" % int(val['p'])
        elif mtt == 3: # number
            if stt == 0:
                return val['n']
            return val['i']
        elif mtt == 4: # string
            return cast_u(val['gc'])['ts']
        elif mtt == 5: # table
            return cast_u(val['gc'])['h']
        elif mtt == 6:
            if stt == 0: # lua closure
                return cast_u(val['gc'])['cl']['l']
            elif stt == 1: # light C function
                return val['f']
            else: # 2 C closure
                return cast_u(val['gc'])['cl']['c']
        elif mtt == 7:
            return "Userdata"
        elif mtt == 8:
            return "Thread"
        return "<Invalid TValue>"

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
        return p['source'].dereference()

    def children(self):
        p = self.val['p']
        yield "1", "linestart"
        yield "2", p['linedefined']
        yield "3", "lineend"
        yield "4", p['lastlinedefined']

class CClosurePrinter:
    "Pretty print lua closure."

    pattern = re.compile(r'^(struct CClosure)|(CClosure)$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "string"

    def to_string(self):
        return "CClosure"

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

LuaStackFunc()
LuaStackCmd()
