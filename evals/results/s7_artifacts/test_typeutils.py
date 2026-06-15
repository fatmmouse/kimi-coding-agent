import pytest
from boltons.typeutils import make_sentinel, issubclass, get_all_subclasses, classproperty


class TestMakeSentinel:
    def test_sentinel_identity(self):
        _MISSING = make_sentinel('_MISSING')
        assert _MISSING is _MISSING

    def test_sentinel_repr(self):
        _MISSING = make_sentinel('_MISSING')
        assert repr(_MISSING) == "Sentinel('_MISSING')"

    def test_sentinel_bool(self):
        _MISSING = make_sentinel('_MISSING')
        assert bool(_MISSING) is False

    def test_sentinel_unique(self):
        a = make_sentinel('a')
        b = make_sentinel('b')
        assert a is not b


class TestIssubclass:
    def test_basic(self):
        assert issubclass(int, object) is True

    def test_tuple_base(self):
        assert issubclass(int, (str, int)) is True

    def test_false(self):
        assert issubclass(int, str) is False

    def test_type_error(self):
        assert issubclass(123, int) is False


class TestGetAllSubclasses:
    def test_basic(self):
        class A:
            pass
        class B(A):
            pass
        class C(B):
            pass
        assert set(get_all_subclasses(A)) == {B, C}

    def test_no_subclasses(self):
        class A:
            pass
        assert get_all_subclasses(A) == []


class TestClassProperty:
    def test_basic(self):
        class Foo:
            @classproperty
            def bar(cls):
                return 42
        assert Foo.bar == 42

    def test_on_instance(self):
        class Foo:
            @classproperty
            def bar(cls):
                return 42
        assert Foo().bar == 42
