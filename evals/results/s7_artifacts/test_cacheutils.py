from boltons.cacheutils import (
    LRU, LRI, cached, cachedmethod, cachedproperty,
    make_cache_key, ThresholdCounter, MinIDMap,
)


class TestLRU:
    def test_basic(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        assert cache['a'] == 1
        assert cache['b'] == 2

    def test_eviction(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        cache['c'] = 3
        assert 'a' not in cache
        assert 'b' in cache
        assert 'c' in cache

    def test_get(self):
        cache = LRU(max_size=2)
        assert cache.get('a') is None
        cache['a'] = 1
        assert cache.get('a') == 1

    def test_pop(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        assert cache.pop('a') == 1
        assert 'a' not in cache

    def test_setdefault(self):
        cache = LRU(max_size=2)
        assert cache.setdefault('a', 1) == 1
        assert cache.setdefault('a', 2) == 1

    def test_clear(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache.clear()
        assert len(cache) == 0

    def test_len(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        assert len(cache) == 2

    def test_iter(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        assert set(cache) == {'a', 'b'}

    def test_copy(self):
        cache = LRU(max_size=2)
        cache['a'] = 1
        cache2 = cache.copy()
        assert cache2['a'] == 1


class TestLRI:
    def test_basic(self):
        cache = LRI(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        assert cache['a'] == 1
        assert cache['b'] == 2

    def test_eviction(self):
        cache = LRI(max_size=2)
        cache['a'] = 1
        cache['b'] = 2
        cache['c'] = 3
        assert len(cache) <= 2


class TestCached:
    def test_basic(self):
        call_count = 0

        @cached(LRI())
        def f(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        assert f(2) == 4
        assert f(2) == 4
        assert call_count == 1


class TestCachedMethod:
    def test_basic(self):
        class MyClass:
            def __init__(self):
                self.cache = LRI()

            @cachedmethod('cache')
            def compute(self, x):
                self.calls = getattr(self, 'calls', 0) + 1
                return x * 2

        obj = MyClass()
        assert obj.compute(2) == 4
        assert obj.compute(2) == 4
        assert obj.calls == 1


class TestCachedProperty:
    def test_basic(self):
        class MyClass:
            def __init__(self):
                self.call_count = 0

            @cachedproperty
            def value(self):
                self.call_count += 1
                return 42

        obj = MyClass()
        assert obj.value == 42
        assert obj.value == 42
        assert obj.call_count == 1


class TestMakeCacheKey:
    def test_basic(self):
        key = make_cache_key((1, 2), {'a': 3})
        t = tuple(key)
        assert t[0] == 1
        assert t[1] == 2
        assert t[3] == ('a', 3)

    def test_no_kwargs(self):
        key = make_cache_key((1, 2), {})
        assert tuple(key) == (1, 2)


class TestThresholdCounter:
    def test_basic(self):
        tc = ThresholdCounter(threshold=0.5)
        tc.add('a')
        tc.add('a')
        tc.add('b')
        assert tc['a'] == 2
        assert tc['b'] == 1

    def test_get_common_count(self):
        tc = ThresholdCounter(threshold=0.5)
        tc.add('a')
        tc.add('a')
        tc.add('b')
        common = tc.get_common_count()
        assert common == 3

    def test_len(self):
        tc = ThresholdCounter(threshold=0.5)
        tc.add('a')
        assert len(tc) == 1


class TestMinIDMap:
    def test_basic(self):
        class Obj:
            pass
        a = Obj()
        b = Obj()
        m = MinIDMap()
        assert m.get(a) == 0
        assert m.get(b) == 1
        assert m.get(a) == 0

    def test_drop(self):
        class Obj:
            pass
        a = Obj()
        m = MinIDMap()
        m.get(a)
        m.drop(a)
        assert m.get(a) == 0
