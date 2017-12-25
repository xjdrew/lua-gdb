# Lua-gdb
gdb extension for lua5.3+.

tested on GNU gdb (Ubuntu 7.11.1-0ubuntu1~16.5) 7.11.1.

## Features

### Pretty printer

* struct TValue
* struct TString
* struct Table
* struct LClosure
* struct CClosure
* struct lua_State

### Command
* luacoroutines [L]

List all coroutines. Without arguments, uses the current value of "L" as the lua_State*. You can provide an alternate lua_State as the first argument.


* luastack [L]

Prints values on the Lua C stack. Without arguments, uses the current value of "L" as the lua_State*. You can provide an alternate lua_State as the first argument.

* luatraceback [L]

Dumps Lua execution stack, as debug.traceback() does. Without arguments, uses the current value of "L" as the lua_State*.  You can provide an alternate lua_State as the first argument.  

* luagetlocal [L [f]]

Print all variables of the function at level 'f' of the stack 'coroutine'. With no arguments, Dump all variables of the current funtion in the stack of 'L'.

## Usage (step by step)

* compile lua with debug symbols
```
cd lua-5.3.4
make linux CFLAGS=-g
```

* start gdb
```
gdb lua-5.3.4/src/lua
```

* set a breakpoint
```
(gdb) break os_time
Breakpoint 1 at 0x42c9fe: file loslib.c, line 324.
```

* run `examples/dbg.lua`
```
(gdb) run examples/dbg.lua
Starting program: /usr/local/bin/lua examples/dbg.lua

Breakpoint 1, os_time (L=0x64b9c8) at loslib.c:324
324     static int os_time (lua_State *L) {
```

will hit the breakpoint `os_time`.

* load the extension
```
(gdb) source lua-gdb.py
Loading Lua Runtime support.
```

* list all coroutines
```
(gdb) luacoroutines
m <coroutine 0x645018> = {[source] = [C]:-1, [func] = 0x427ff9 <luaB_coresume>}
  <coroutine 0x64b9c8> = {[source] = [C]:-1, [func] = 0x42c9f2 <os_time>}
  <coroutine 0x645638> = {[source] = [C]:-1, [func] = ?}
```

* dump stack
```
(gdb) luastack 0x64b9c8
#0      0x64bb30        <os_time>
#1      0x64bb20        2
#2      0x64bb10        5
#3      0x64bb00        10
#4      0x64baf0        "kkk"
#5      0x64bae0        1
#6      0x64bad0        "nil"
#7      0x64bac0        "nil"
#8      0x64bab0        <lclosure 0x64b920> = {[file] = "@examples/dbg.lua", [linestart] = 17, [lineend] = 20, [nupvalues] = 1 '\001'}
```

* dump traceback
```
(gdb) luatraceback 0x64b9c8
stack traceback:
        [C]:-1: in 0x42c9f2 <os_time>
        "@examples/dbg.lua":19: in ?
```

* list all variables of a closure in the traceback
```
(gdb) luagetlocal 0x64b9c8 1
call info: "@examples/dbg.lua":19: in ?
        upval _ENV = 3.2627937150349253e-317
        ..... (*vararg) = 1
        ..... (*vararg) = "kkk"
        local x = 10
        local i = 5
        local n = 2
```

* enjoy it!
