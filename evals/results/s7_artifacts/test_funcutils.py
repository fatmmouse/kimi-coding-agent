from boltons.funcutils import (
    wraps, FunctionBuilder, format_invocation,
    update_wrapper, partial_ordering, noop, once,
)


class TestWraps:
    def test_basic(self):
        def original(a, b):
            return a + b

        @wraps(original)
        def wrapper(a, b):
            return original(a, b)

        assert wrapper.__name__ == 'original'
        assert wrapper(1, 2) == 3

    def test_with_injected(self):
        def original(a, b):
            return a + b

        @wraps(original, injected='b')
        def wrapper(a, b):
            return original(a, b)

        assert wrapper.__name__ == 'original'


class TestFunctionBuilder:
    def test_from_func(self):
        def original(x, y=10):
            return x + y

        fb = FunctionBuilder.from_func(original)
        assert fb.name == 'original'
        assert fb.args == ['x', 'y']
        assert fb.defaults == (10,)

    def test_get_invocation_str(self):
        def original(x, y=10):
            return x + y

        fb = FunctionBuilder.from_func(original)
        inv = fb.get_invocation_str()
        assert 'x' in inv

    def test_add_arg(self):
        fb = FunctionBuilder('foo', body='return x')
        fb.add_arg('x', default=5)
        assert 'x' in fb.args

    def test_get_func(self):
        fb = FunctionBuilder('return_five', body='return 5')
        f = fb.get_func()
        assert f() == 5

    def test_doc(self):
        fb = FunctionBuilder('foo', body='return 1', doc='A docstring')
        f = fb.get_func()
        assert f.__doc__ == 'A docstring'


class TestFormatInvocation:
    def test_basic(self):
        assert format_invocation('foo', [1, 2], {'a': 3}) == 'foo(1, 2, a=3)'

    def test_no_args(self):
        assert format_invocation('foo') == 'foo()'


class TestNoop:
    def test_returns_none(self):
        assert noop() is None

    def test_accepts_args(self):
        assert noop(1, 2, a=3) is None


class TestOnce:
    def test_basic(self):
        call_count = 0

        @once
        def f():
            nonlocal call_count
            call_count += 1
            return 42

        assert f() == 42
        assert f() == 42
        assert call_count == 1


class TestPartialOrdering:
    def test_basic(self):
        @partial_ordering
        class Point:
            def __init__(self, x):
                self.x = x

            def __eq__(self, other):
                return self.x == other.x

            def __lt__(self, other):
                return self.x < other.x

        p1 = Point(1)
        p2 = Point(2)
        assert p1 < p2
        assert p2 > p1

    def test_eq(self):
        @partial_ordering
        class Point:
            def __init__(self, x):
                self.x = x

            def __eq__(self, other):
                return self.x == other.x

            def __lt__(self, other):
                return self.x < other.x

        p1 = Point(1)
        p2 = Point(1)
        assert p1 == p2
