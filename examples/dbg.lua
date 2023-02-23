local t = {
    "hello",
    "world",
    1, 2, 3,
    vacant = nil,
    boolean = true,
    int = 5,
    float = 3.83,
    shrstr = 'short',
    lngstr = 'long ' .. string.rep('s', 50),
    func = function() end,
    co = coroutine.create(function() end),
}
-- hole
t[4] = nil
print(#t)
-- loop
t.t = t

local function d1(x, i, ...)
    local n = select('#', ...)
    return os.time() + x + i + n
end

local function d0(x, t)
    local limit = math.random(20)
    if x > limit then
        local c = d1(0, 1) + 5
    end

    local co = coroutine.create(d1)
    local i = 5
    local j = 1
    local k = "kkk"
    local ok, v = coroutine.resume(co, x, i, j, k)
    return v
end

print(d0(10, t))
