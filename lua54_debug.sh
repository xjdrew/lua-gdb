#for lua5.4
#gdb中加载: source ./lua54_debug.sh
#命令
#1、luabt L 显示调用栈（参数为L)

# luabt 显示调用栈
define luabt
	set $L = $0
	print $L
	set $ci = $L->ci
	while($ci)
		set $func = (StackValue*)$ci->func
		set $tt = ((TValue)($func->val)->value_)->tt_ & 0x3f
		if ($tt==6)
			set $p = ((LClosure *)$func->val->value_.gc)->p
			set $filename = (char*)($p->source->contents)
			set $lineinfo = $p->lineinfo
			set $pc1 = (int)(((int)$ci->u->l->savedpc)-(int)$p->code)/4 -1
			set $lineno = 0

			set $basepc = 0
			set $baseline = 0
			set $MAXIWTHABS = 128
			set $ABSLINEINFO = -0x80
			if ($lineinfo == 0)
				set $lineno = -1
			else
				set $sizeabslineinfo = $p->sizeabslineinfo
				if ($sizeabslineinfo == 0 || (long)$pc1 < (long)$p->abslineinfo[0].pc)
					set $basepc = (long)(-1)
					set $baseline = $p->linedefined
				else
					set $pcc = ((unsigned int)$pc1)
					set $i = $pcc / $MAXIWTHABS - 1
					while ((long)($i + 1) < (long)$p->sizeabslineinfo && (long)$pc1 >= (long)$p->abslineinfo[$i + 1].pc)
						set $i=$i+1
					end
					set $basepc = (long)($p->abslineinfo[$i].pc)
					set $baseline = $p->abslineinfo[$i].line
				end
				while((long)$basepc < (long)$pc1)
					set $basepc = $basepc + 1
					set $baseline = $baseline + $p->lineinfo[$basepc]
				end
				set $lineno = $baseline
			end
			printf "LUA FUNCTION : %s:%d\n", $filename, $lineno
		end
		
		if($tt==0x16)
			set $f = $func->val->value_->f
			printf "LC  FUNCTION :"
			info line *$f
		end
		
		if($tt==0x26)
			set $f = ((CClosure *)$func->val->value_.gc)->f
			printf "C   FUNCTION :"
			info line *$f
		end

		set $ci = $ci->previous
	end
end