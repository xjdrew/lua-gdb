# Lua-gdb
gdb extension for lua5.3+.

## Usage

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


* luastack [coroutine]

Prints values on the Lua C stack. Without arguments, uses the current value of "L" as the lua_State*. You can provide an alternate lua_State as the first argument.

* luatraceback  [coroutine]

Dumps Lua execution stack, as debug.traceback() does. Without arguments, uses the current value of "L" as the lua_State*.  You can provide an alternate lua_State as the first argument.  

* luagetlocal [coroutine [f]]

Print all variables of the function at level 'f' of the stack 'coroutine'. With no arguments, Dump all variables of the current funtion in the stack of 'L'.
