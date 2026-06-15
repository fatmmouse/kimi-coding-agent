import pytest
from boltons.dictutils import OrderedMultiDict, FrozenDict, ManyToMany


class TestOrderedMultiDict:
    def test_init_empty(self):
        omd = OrderedMultiDict()
        assert len(omd) == 0
        assert list(omd) == []

    def test_init_from_dict(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.items()) == [('a', 1), ('b', 2)]

    def test_add(self):
        omd = OrderedMultiDict()
        omd.add('a', 1)
        omd.add('a', 2)
        assert omd.getlist('a') == [1, 2]

    def test_get(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2)])
        assert omd.get('a') == 2

    def test_getlist(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2)])
        assert omd.getlist('a') == [1, 2]

    def test_setitem(self):
        omd = OrderedMultiDict()
        omd['a'] = 1
        assert omd['a'] == 1
        omd['a'] = 2
        assert omd['a'] == 2
        assert omd.getlist('a') == [2]

    def test_delitem(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        del omd['a']
        assert 'a' not in omd
        assert omd['b'] == 2

    def test_contains(self):
        omd = OrderedMultiDict([('a', 1)])
        assert 'a' in omd
        assert 'b' not in omd

    def test_keys(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.keys()) == ['a', 'b']

    def test_values(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.values()) == [1, 2]

    def test_items(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.items()) == [('a', 1), ('b', 2)]

    def test_pop(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert omd.pop('a') == 1
        assert 'a' not in omd

    def test_poplast(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert omd.poplast() == 2
        assert list(omd.items()) == [('a', 1)]

    def test_update(self):
        omd = OrderedMultiDict()
        omd.update([('a', 1), ('b', 2)])
        assert list(omd.items()) == [('a', 1), ('b', 2)]

    def test_len(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2), ('b', 3)])
        assert len(omd) == 2

    def test_iter(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd) == ['a', 'b']

    def test_eq(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert omd == {'a': 1, 'b': 2}

    def test_repr(self):
        omd = OrderedMultiDict([('a', 1)])
        assert repr(omd) == "OrderedMultiDict([('a', 1)])"

    def test_inverted(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2), ('a', 3)])
        inv = omd.inverted()
        assert inv.getlist(1) == ['a']
        assert inv.getlist(2) == ['b']
        assert inv.getlist(3) == ['a']

    def test_counts(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2), ('b', 3)])
        assert omd.counts() == {'a': 2, 'b': 1}

    def test_iteritems(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.iteritems()) == [('a', 1), ('b', 2)]

    def test_iterkeys(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.iterkeys()) == ['a', 'b']

    def test_itervalues(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert list(omd.itervalues()) == [1, 2]

    def test_clear(self):
        omd = OrderedMultiDict([('a', 1)])
        omd.clear()
        assert len(omd) == 0

    def test_copy(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2)])
        omd2 = omd.copy()
        assert omd2.getlist('a') == [1, 2]
        omd2.add('a', 3)
        assert omd.getlist('a') == [1, 2]

    def test_fromkeys(self):
        omd = OrderedMultiDict.fromkeys(['a', 'b'], 1)
        assert list(omd.items()) == [('a', 1), ('b', 1)]

    def test_setdefault(self):
        omd = OrderedMultiDict()
        assert omd.setdefault('a', 1) == 1
        assert omd.setdefault('a', 2) == 1

    def test_popitem(self):
        omd = OrderedMultiDict([('a', 1), ('b', 2)])
        assert omd.popitem() == ('b', [2])
        assert omd.popitem() == ('a', [1])

    def test_popall(self):
        omd = OrderedMultiDict([('a', 1), ('a', 2), ('b', 3)])
        assert omd.popall('a') == [1, 2]
        assert 'a' not in omd

    def test_sorted(self):
        omd = OrderedMultiDict([('b', 2), ('a', 1)])
        sorted_omd = omd.sorted()
        assert list(sorted_omd.items()) == [('a', 1), ('b', 2)]


class TestFrozenDict:
    def test_init_empty(self):
        fd = FrozenDict()
        assert len(fd) == 0
        assert list(fd) == []

    def test_init_from_dict(self):
        fd = FrozenDict({'a': 1, 'b': 2})
        assert fd['a'] == 1
        assert fd['b'] == 2

    def test_immutable(self):
        fd = FrozenDict({'a': 1})
        with pytest.raises(TypeError):
            fd['a'] = 2
        with pytest.raises(TypeError):
            del fd['a']
        with pytest.raises(TypeError):
            fd.update({'b': 2})
        with pytest.raises(TypeError):
            fd.setdefault('b', 2)
        with pytest.raises(TypeError):
            fd.pop('a')
        with pytest.raises(TypeError):
            fd.popitem()
        with pytest.raises(TypeError):
            fd.clear()

    def test_hashable(self):
        fd = FrozenDict({'a': 1})
        assert hash(fd) == hash(fd)
        d = {fd: 1}
        assert d[fd] == 1

    def test_eq(self):
        fd = FrozenDict({'a': 1})
        assert fd == {'a': 1}

    def test_repr(self):
        fd = FrozenDict({'a': 1})
        assert repr(fd) == "FrozenDict({'a': 1})"

    def test_copy(self):
        fd = FrozenDict({'a': 1})
        assert fd.__copy__() is fd

    def test_reduce(self):
        fd = FrozenDict({'a': 1})
        assert fd.__reduce_ex__(2) == (FrozenDict, ({'a': 1},))


class TestManyToMany:
    def test_init_empty(self):
        m2m = ManyToMany()
        assert len(m2m) == 0
        assert list(m2m) == []

    def test_init_from_dict(self):
        m2m = ManyToMany([('a', 'b'), ('a', 'c')])
        assert 'a' in m2m
        assert m2m['a'] == {'b', 'c'}

    def test_add(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        assert m2m['a'] == {'b'}
        assert m2m.inv['b'] == {'a'}

    def test_remove(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        m2m.remove('a', 'b')
        assert 'a' not in m2m
        assert 'b' not in m2m.inv

    def test_getitem(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        m2m.add('a', 'c')
        assert m2m['a'] == {'b', 'c'}

    def test_setitem(self):
        m2m = ManyToMany()
        m2m['a'] = 'b'
        assert m2m['a'] == {'b'}

    def test_delitem(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        del m2m['a']
        assert 'a' not in m2m
        assert 'b' not in m2m.inv

    def test_contains(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        assert 'a' in m2m
        assert 'b' in m2m.inv

    def test_len(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        m2m.add('a', 'c')
        assert len(m2m) == 1
        assert len(m2m.inv) == 2

    def test_iter(self):
        m2m = ManyToMany()
        m2m.add('a', 'b')
        assert list(m2m) == ['a']
        assert list(m2m.inv) == ['b']

    def test_eq(self):
        m2m = ManyToMany([('a', 'b')])
        assert m2m == ManyToMany([('a', 'b')])

    def test_repr(self):
        m2m = ManyToMany([('a', 'b')])
        assert repr(m2m) == "ManyToMany([('a', 'b')])"

    def test_keys(self):
        m2m = ManyToMany([('a', 'b'), ('c', 'd')])
        assert set(m2m.keys()) == {'a', 'c'}

    def test_values(self):
        m2m = ManyToMany([('a', 'b'), ('c', 'd')])
        vals = list(m2m.data.values())
        assert {'b'} in vals
        assert {'d'} in vals

    def test_items(self):
        m2m = ManyToMany([('a', 'b')])
        assert list(m2m.data.items()) == [('a', {'b'})]
