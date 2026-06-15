import pytest
from boltons.setutils import IndexedSet, _ComplementSet as ComplementSet


class TestIndexedSet:
    def test_init_empty(self):
        s = IndexedSet()
        assert len(s) == 0
        assert list(s) == []

    def test_init_from_list(self):
        s = IndexedSet([1, 2, 3])
        assert len(s) == 3
        assert list(s) == [1, 2, 3]

    def test_add(self):
        s = IndexedSet()
        s.add(1)
        s.add(2)
        assert list(s) == [1, 2]

    def test_add_duplicate(self):
        s = IndexedSet([1])
        s.add(1)
        assert len(s) == 1
        assert list(s) == [1]

    def test_discard(self):
        s = IndexedSet([1, 2, 3])
        s.discard(2)
        assert list(s) == [1, 3]

    def test_remove(self):
        s = IndexedSet([1, 2, 3])
        s.remove(2)
        assert list(s) == [1, 3]

    def test_remove_missing(self):
        s = IndexedSet([1, 2, 3])
        with pytest.raises(KeyError):
            s.remove(4)

    def test_pop(self):
        s = IndexedSet([1, 2, 3])
        assert s.pop() == 3
        assert list(s) == [1, 2]

    def test_getitem(self):
        s = IndexedSet([1, 2, 3])
        assert s[0] == 1
        assert s[1] == 2
        assert s[2] == 3

    def test_getitem_negative(self):
        s = IndexedSet([1, 2, 3])
        assert s[-1] == 3

    def test_contains(self):
        s = IndexedSet([1, 2, 3])
        assert 2 in s
        assert 4 not in s

    def test_index(self):
        s = IndexedSet([1, 2, 3])
        assert s.index(2) == 1

    def test_index_missing(self):
        s = IndexedSet([1, 2, 3])
        with pytest.raises(ValueError):
            s.index(4)

    def test_slice(self):
        s = IndexedSet([1, 2, 3, 4, 5])
        assert list(s[1:4]) == [2, 3, 4]

    def test_union(self):
        s = IndexedSet([1, 2])
        s2 = s | {3, 4}
        assert isinstance(s2, IndexedSet)
        assert list(s2) == [1, 2, 3, 4]

    def test_intersection(self):
        s = IndexedSet([1, 2, 3])
        s2 = s & {2, 3, 4}
        assert isinstance(s2, IndexedSet)
        assert list(s2) == [2, 3]

    def test_difference(self):
        s = IndexedSet([1, 2, 3])
        s2 = s - {2}
        assert isinstance(s2, IndexedSet)
        assert list(s2) == [1, 3]

    def test_symmetric_difference(self):
        s = IndexedSet([1, 2, 3])
        s2 = s ^ {2, 4}
        assert isinstance(s2, IndexedSet)
        assert list(s2) == [1, 3, 4]

    def test_issubset(self):
        s = IndexedSet([1, 2])
        assert s.issubset({1, 2, 3})
        assert not s.issubset({1})

    def test_issuperset(self):
        s = IndexedSet([1, 2, 3])
        assert s.issuperset({1, 2})
        assert not s.issuperset({1, 4})

    def test_clear(self):
        s = IndexedSet([1, 2, 3])
        s.clear()
        assert len(s) == 0

    def test_update(self):
        s = IndexedSet([1, 2])
        s.update([3, 4])
        assert list(s) == [1, 2, 3, 4]

    def test_iter(self):
        s = IndexedSet([1, 2, 3])
        assert list(iter(s)) == [1, 2, 3]

    def test_reversed(self):
        s = IndexedSet([1, 2, 3])
        assert list(reversed(s)) == [3, 2, 1]

    def test_bool(self):
        s = IndexedSet()
        assert not s
        s.add(1)
        assert s

    def test_hash(self):
        s = IndexedSet([1, 2, 3])
        with pytest.raises(TypeError):
            hash(s)

    def test_copy(self):
        s = IndexedSet([1, 2, 3])
        s2 = set(s)
        assert s2 == {1, 2, 3}


class TestComplementSet:
    def test_init_from_set(self):
        s = ComplementSet({1, 2, 3})
        assert len(s) == 3
        assert set(s) == {1, 2, 3}

    def test_complement(self):
        s = ComplementSet({1, 2, 3})
        c = ~s
        assert 1 not in c
        assert 4 in c

    def test_union(self):
        s = ComplementSet({1, 2})
        s2 = s | {3, 4}
        assert set(s2) == {1, 2, 3, 4}

    def test_intersection(self):
        s = ComplementSet({1, 2, 3})
        s2 = s & {2, 3, 4}
        assert set(s2) == {2, 3}

    def test_difference(self):
        s = ComplementSet({1, 2, 3})
        s2 = s - {2}
        assert set(s2) == {1, 3}

    def test_symmetric_difference(self):
        s = ComplementSet({1, 2, 3})
        s2 = s ^ {2, 4}
        assert set(s2) == {1, 3, 4}

    def test_contains(self):
        s = ComplementSet({1, 2, 3})
        assert 2 in s
        assert 4 not in s

    def test_bool(self):
        s = ComplementSet({1})
        assert s
        s = ComplementSet(frozenset())
        assert not s

    def test_complement_bool(self):
        c = ~ComplementSet(frozenset())
        assert c

    def test_complement_len_raises(self):
        c = ~ComplementSet({1, 2})
        with pytest.raises(NotImplementedError):
            len(c)

    def test_complement_iter_raises(self):
        c = ~ComplementSet({1, 2})
        with pytest.raises(NotImplementedError):
            list(c)

    def test_eq(self):
        s = ComplementSet({1, 2, 3})
        assert s == {1, 2, 3}
        assert s == ComplementSet({1, 2, 3})

    def test_hash(self):
        s = ComplementSet(frozenset({1, 2, 3}))
        assert hash(s) == hash(ComplementSet(frozenset({1, 2, 3})))
