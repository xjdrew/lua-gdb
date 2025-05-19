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


# gdb.Value to specific type tt
def cast_to_type_pointer(o, tt):
    t = gdb.lookup_type(tt)
    return o.cast(t.pointer())

# basic types
LUA_TNIL            =0
LUA_TBOOLEAN        =1
LUA_TLIGHTUSERDATA  =2
LUA_TNUMBER	        =3
LUA_TSTRING	        =4
LUA_TTABLE          =5
LUA_TFUNCTION       =6
LUA_TUSERDATA       =7
LUA_TTHREAD	        =8

def makevariant(t, v): return t | (v << 4)
def ctb(t): return t | (1 << 6)

LUA_VFALSE = makevariant(LUA_TBOOLEAN, 0)
LUA_VTRUE  = makevariant(LUA_TBOOLEAN, 1)

# test type
def checktype(o, t): return o['tt_']&0x0f == t
def checktag(o, t): return o['tt_'] == t

# input GCObject*
def cast_u(o):
    return cast_to_type_pointer(o, "union GCUnion")

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
def bvalue(o): return checktype(o, LUA_VTRUE)

# <TValue> -> <lua_State>
def thvalue(o): return cast_u(o['value_']['gc'])['th']

LUA_VNUMINT = makevariant(LUA_TNUMBER, 0)
LUA_VNUMFLT = makevariant(LUA_TNUMBER, 1)

def ttisnumber(o): return checktype(o, LUA_TNUMBER)
def ttisfloat(o): return checktag(o, LUA_VNUMFLT)
def ttisinteger(o): return checktag(o, LUA_VNUMINT)
def ttisnil(o): return checktype(o, LUA_TNIL)
def ttisboolean(o): return checktype(o, LUA_TBOOLEAN)

LUA_VLIGHTUSERDATA = makevariant(LUA_TLIGHTUSERDATA, 0)
LUA_VUSERDATA = makevariant(LUA_TUSERDATA, 0)

def ttislightuserdata(o): return checktag(o, LUA_VLIGHTUSERDATA)
def ttisfulluserdata(o): return checktag(o, ctb(LUA_VUSERDATA))

LUA_VSHRSTR = makevariant(LUA_TSTRING, 0)
LUA_VLNGSTR = makevariant(LUA_TSTRING, 1)

def ttisstring(o): return checktype(o, LUA_TSTRING)
def ttisshrstring(o): return checktype(o, ctb(LUA_VSHRSTR))
def ttislngstring(o): return checktype(o, ctb(LUA_VLNGSTR))

LUA_VTABLE = makevariant(LUA_TTABLE, 0)

def ttistable(o): return checktag(o, ctb(LUA_VTABLE))

LUA_VLCL = makevariant(LUA_TFUNCTION, 0)
LUA_VLCF = makevariant(LUA_TFUNCTION, 1)
LUA_VCCL = makevariant(LUA_TFUNCTION, 2)

def ttisfunction(o): return checktype(o, LUA_TFUNCTION)
def ttisclosure(o): return o['tt_'] & 0x1f == LUA_VLCL
def ttisCclosure(o): return checktag(o, ctb(LUA_VCCL))
def ttisLclosure(o): return checktag(o, ctb(LUA_VLCL))
def ttislcf(o): return checktag(o, LUA_VLCF)

LUA_VTHREAD = makevariant(LUA_TTHREAD, 0)

def ttisthread(o): return checktag(o, ctb(LUA_VTHREAD))

# gdb.Value to string
def value_to_string(val):
    s = str(val.dereference())
    if len(s) > 1 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s

def cast_luaState(o):
    return cast_to_type_pointer(o, "struct lua_State")

#
# Value wrappers
#

# StackValue to TValue
def s2v(stk): return stk['val']

# struct lua_TValue
class TValueValue:
    "Wrapper for TValue value."

    def __init__(self, val):
        self.val = val

    def upvars(self):
        if ttisCclosure(self.val):
            f = clCvalue(self.val)
            for i in xrange(f['nupvalues']):
                yield "(%d)" % (i+1), cast_to_type_pointer(f['upvalue'], "TValue") + i
        elif ttisLclosure(self.val):
            f = clLvalue(self.val)
            proto = f['p']
            for i in xrange(int(proto['sizeupvalues'])):
                uv = cast_to_type_pointer(f['upvals'][i], "struct UpVal")
                value = uv['v']
                name = (proto['upvalues'] + i)['name']
                if name:
                    yield value_to_string(name), value
                else:
                    yield "(no name)", value

# struct CallInfo
class CallInfoValue:
    "Wrapper for CallInfo value."

    CIST_C = 1<<1
    CIST_TAIL = 1<<5
    CIST_FIN = 1<<7

    def __init__(self, L, ci):
        self.L = L
        self.ci = ci

        self.name = None
        self.namewhat = None

        if self.is_lua():
            proto = clLvalue(s2v(self.ci['func']))['p']
            self.proto = proto

            if not proto['source']:
                self.source = "?"
            else:
                self.source = proto['source'].dereference()

            self.linedefined = proto['linedefined']
            self.lastlinedefined = proto['lastlinedefined']

            if self.linedefined == 0:
                self.what = "main"
            else:
                self.what = "Lua"

            self.currentpc = (self.ci['u']['l']['savedpc'] - proto['code']) - 1 
            self.currentline = self.getfuncline(proto, self.currentpc)

        else:
            self.source = "[C]"
            self.linedefined = -1
            self.lastlinedefined = -1
            self.what = "C"
            self.currentline = -1

        if self.is_fin():
            self.name = "__gc"
            self.namewhat = "metamethod"

    def getfuncline(self, proto, pc):
        """
            ldebug.c luaG_getfuncline
        """
        if not proto['lineinfo']:
            return -1
        def getbaseline(proto, pc):
            if proto['sizeabslineinfo'] == 0 or pc < proto['abslineinfo'][0]['pc']:
                return -1, proto['linedefined']
            if pc >= proto['abslineinfo'][proto['sizeabslineinfo']-1]['pc']:
                i = proto['sizeabslineinfo']-1
            else:
                j = proto['sizeabslineinfo']-1
                i = 0
                while i < j - 1:
                    m = (j + i) / 2
                    if pc >= proto['abslineinfo'][m]['pc']:
                        i = m
                    else:
                        j = m
            return proto['abslineinfo'][i]['pc'], proto['abslineinfo'][i]['line']
        basepc, baseline = getbaseline(proto, pc)
        while basepc < pc:
            basepc+=1
            baseline += proto['lineinfo'][basepc]
        return baseline

    @property
    def funcname(self):
        if self.what == "main":
            return "main chunk"

        if self.namewhat:
            return "%s '%s'" % (self.namewhat, self.name)

        func = s2v(self.ci['func'])
        if ttislcf(func):
            return "%s" % fvalue(func)

        if ttisCclosure(func):
            return "%s" % clCvalue(func)['f']

        return '?'

    def is_lua(self):
        return not (self.ci['callstatus'] & CallInfoValue.CIST_C)

    def is_tailcall(self):
        return self.ci['callstatus'] & CallInfoValue.CIST_TAIL

    def is_fin(self):
        return self.ci['callstatus'] & CallInfoValue.CIST_FIN
    
    # stack frame information
    def frame_info(self):
        return '%s:%d: in %s' % (self.source, self.currentline, self.funcname)

    # luastack:
    #   vararg(1)
    #   ...
    #   vararg(nextraargs) <- ci->u.l.nextraargs nextra vararg
    #   callee             <- ci->func
    #   arg(1)
    #   ...
    #   arg(n)
    #   local(1)
    #   ...
    #   local(n)
    @property
    def stack_base(self):
        return self.ci['func'] + 1

    @property
    def stack_top(self):
        if self.ci == self.L['ci']:
            return self.L['top']
        else:
            nextcv = CallInfoValue(self.L, self.ci['next'])
            return nextcv.stack_base - 1

    def getlocalname(self, n):
        if not self.is_lua():
            return None

        proto = self.proto
        currentpc = self.currentpc

        i = 0
        while i< proto['sizelocvars']:
            locvar = proto['locvars'] + i
            if locvar['startpc'] <= currentpc and currentpc < locvar['endpc']:
                n = n - 1
                if n == 0:
                    return value_to_string(locvar['varname'])
            i = i + 1
        return None

    def upvars(self):
        tv = TValueValue(s2v(self.ci['func']))
        return tv.upvars()

    def varargs(self):
        if not self.is_lua():
            return

        if self.proto['is_vararg'] != 1:
            return 

        nextra = self.ci['u']['l']['nextraargs']
        for i in xrange(nextra):
            yield "(*vararg)", s2v(self.ci['func'] - (i+1)).address

    def locvars(self):
        base = self.stack_base
        limit = self.stack_top
        i = 1
        while True:
            name = self.getlocalname(i)
            if not name:
                if (limit - base) >= i:
                    if self.is_lua():
                        name = "(temporary)"
                    else:
                        name = "(C temporary)"
                else:
                    return
            yield name, s2v(base + i - 1).address
            i = i + 1

#
# Pretty Printers
#

def tvaluestring(value):
    if ttisnil(value): # nil
            return "nil"
    elif ttisboolean(value): # boolean
        if bvalue(value) > 0:
            return "True"
        else:
            return "False"
    elif ttisnumber(value): # number
        if ttisfloat(value):
            return fltvalue(value)
        elif ttisinteger(value):
            return ivalue(value)
    elif ttisstring(value): # string
        return tsvalue(value)
    elif ttistable(value): # table
        return hvalue(value)
    elif ttisfunction(value):
        if ttisLclosure(value): # lua closure
            return clLvalue(value)
        elif ttislcf(value): # light C function
            return fvalue(value)
        elif ttisCclosure(value): # 2 C closure
            return clCvalue(value)
    elif ttisfulluserdata(value):
        return "Userdata"
    elif ttislightuserdata(value): # lightuserdata
        return "<lightuserdata 0x%x>" % int(pvalue(value))
    elif ttisthread(value):
        return thvalue(value)
    assert False, value['tt_']

class TValuePrinter:
    "Pretty print lua value."

    pattern = re.compile(r'^(struct TValue)|(TValue)$')

    def __init__(self, val):
        self.val = val

    def to_string(self):
        return tvaluestring(self.val)

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
        s = self.val["contents"]
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
        sizearray = self.realasize()
        i = 0
        while i < sizearray:
            val = self.val['array'][i]
            if ttisnil(val):
                i = i + 1
                continue
            yield str(2*i), i
            yield str(2*i + 1), val
            i = i + 1

        # hash part
        j = 0
        last = 1 << self.val['lsizenode']
        while j < last:
            node = self.val['node'][j]
            j = j + 1
            value = node['i_val']
            if ttisnil(value):
                continue
            fakeTValue = {
                "tt_": node['u']['key_tt'],
                "value_": node['u']['key_val']
            }
            yield str(2*i + 2*j), tvaluestring(fakeTValue)
            yield str(2*i + 2*j + 1), value

        if setMarked:
            TablePrinter.marked = None

    def realasize(self):
        def isrealasize(self): return (self.val['flags'] & (1<<7)) == 0
        def ispow2(x): return (((x) & ((x) - 1)) == 0)
        if (isrealasize(self) or ispow2(self.val['alimit'])):
            return self.val['alimit']
        else:
            size = self.val['alimit']
            size |= (size >> 1)
            size |= (size >> 2)
            size |= (size >> 4)
            size |= (size >> 8)
            size |= (size >> 16)
            size += 1
            return size


class LClosurePrinter:
    "Pretty print lua closure."

    pattern = re.compile(r'^(struct LClosure)|(LClosure)$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "map"

    def to_string(self):
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
        return "<cclosure 0x%x>" % int(self.val.address)

    def children(self):
        yield "1", "nupvalues"
        yield "2", self.val['nupvalues']

class LuaStatePrinter:
    "Pretty print lua_State."

    pattern = re.compile(r'^struct lua_State$')

    def __init__(self, val):
        self.val = val

    def display_hint(self):
        return "map"

    def to_string(self):
        return "<coroutine 0x%x>" % int(self.val.address)

    def children(self):
        cv = CallInfoValue(self.val, self.val['ci'])
        yield "1", "source"
        yield "2", "%s:%d" % (cv.source, cv.currentline)
        yield "3", "func"
        yield "4", cv.funcname

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

class LuaStackCmd(gdb.Command):
    """luastack [L]
Prints values on the Lua C stack. Without arguments, uses the current value of "L"
as the lua_State*. You can provide an alternate lua_State as the first argument."""

    def __init__(self):
        gdb.Command.__init__(self, "luastack", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty):
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = cast_luaState(gdb.parse_and_eval(argv[0]))
        else:
            L = gdb.parse_and_eval("L")

        stack = L['top'] - 1
        i = 0
        while stack > L['stack']:
            print("#%d\t0x%x\t%s" % (i, int(stack), stack.dereference()))
            stack = stack - 1
            i = i + 1

class LuaTracebackCmd(gdb.Command):
    """luabacktrace [L]
Dumps Lua execution stack, as debug.traceback() does. Without
arguments, uses the current value of "L" as the
lua_State*. You can provide an alternate lua_State as the
first argument.
    """
    def __init__(self):
        gdb.Command.__init__(self, "luatraceback", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty): 
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = cast_luaState(gdb.parse_and_eval(argv[0]))
        else:
            L = gdb.parse_and_eval("L")

        ci = L['ci']
        print("stack traceback:")
        while ci != L['base_ci'].address:
            cv = CallInfoValue(L, ci)
            print('\t%s' % (cv.frame_info()))
            if cv.is_tailcall():
                print('\t(...tail calls...)')
            ci = ci['previous']


class LuaCoroutinesCmd(gdb.Command):
    """luacoroutines [L]
List all coroutines. Without arguments, uses the current value of "L" as the
lua_State*. You can provide an alternate lua_State as the
first argument.
    """
    def __init__(self):
        gdb.Command.__init__(self, "luacoroutines", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty): 
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = cast_luaState(gdb.parse_and_eval(argv[0]))
        else:
            L = gdb.parse_and_eval("L")

        # global_State
        lG = L['l_G']

        # mainthread
        print("m", lG['mainthread'].dereference())

        obj = lG['allgc']
        while obj:
            if obj['tt'] == 8:
                print(" ", cast_u(obj)['th'])
            obj = obj['next']

class LuaGetLocalCmd(gdb.Command):
    """luagetlocal [L [f]]
Print all local variables of the function at level 'f' of the stack 'thread'. 
With no arguments, Dump all local variable of the current funtion in the stack of 'L';
    """
    def __init__(self):
        gdb.Command.__init__(self, "luagetlocal", gdb.COMMAND_STACK, gdb.COMPLETE_NONE)

    def invoke(self, args, _from_tty):
        argv = gdb.string_to_argv(args)
        if len(argv) > 0:
            L = cast_luaState(gdb.parse_and_eval(argv[0]))
        else:
            L = gdb.parse_and_eval("L")

        if len(argv) > 1:
            arg2 = gdb.parse_and_eval(argv[1])
        else:
            arg2 = gdb.parse_and_eval("0")

        level = arg2 
        ci = L['ci']
        while level > 0: 
            ci = ci['previous']
            if ci == L['base_ci'].address:
                break
            level = level - 1

        if level != 0:
            print("No function at level %d" % arg2)
            return

        cv = CallInfoValue(L, ci)
        print("call info: %s" % cv.frame_info())

        for name, var in cv.upvars():
            print("\tupval %s = %s" % (name, var.dereference()))

        for name, var in cv.varargs():
            print("\t..... %s = %s" % (name, var.dereference()))

        for name, var in cv.locvars():
            print("\tlocal %s = %s" % (name, var.dereference()))

LuaStackCmd()
LuaTracebackCmd()
LuaCoroutinesCmd()
LuaGetLocalCmd()