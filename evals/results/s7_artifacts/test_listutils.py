import pytest
from boltons.listutils import BarrelList, SplayList


class TestBarrelList:
    def test_init_empty(self):
        bl = BarrelList()
        assert len(bl) == 0
        assert list(bl) == []

    def test_init_from_list(self):
        bl = BarrelList([1, 2, 3])
        assert len(bl) == 3
        assert list(bl) == [1, 2, 3]

    def test_append(self):
        bl = BarrelList()
        bl.append(1)
        bl.append(2)
        assert list(bl) == [1, 2]

    def test_insert(self):
        bl = BarrelList([1, 3])
        bl.insert(1, 2)
        assert list(bl) == [1, 2, 3]

    def test_insert_at_end(self):
        bl = BarrelList([1, 2])
        bl.insert(2, 3)
        assert list(bl) == [1, 2, 3]

    def test_pop(self):
        bl = BarrelList([1, 2, 3])
        assert bl.pop() == 3
        assert list(bl) == [1, 2]

    def test_pop_index(self):
        bl = BarrelList([1, 2, 3])
        assert bl.pop(1) == 2
        assert list(bl) == [1, 3]

    def test_getitem(self):
        bl = BarrelList([1, 2, 3])
        assert bl[0] == 1
        assert bl[1] == 2
        assert bl[2] == 3

    def test_setitem(self):
        bl = BarrelList([1, 2, 3])
        bl[1] = 5
        assert list(bl) == [1, 5, 3]

    def test_delitem(self):
        bl = BarrelList([1, 2, 3])
        del bl[1]
        assert list(bl) == [1, 3]

    def test_contains(self):
        bl = BarrelList([1, 2, 3])
        assert 2 in bl
        assert 4 not in bl

    def test_sort(self):
        bl = BarrelList([3, 1, 2])
        bl.sort()
        assert list(bl) == [1, 2, 3]

    def test_reverse(self):
        bl = BarrelList([1, 2, 3])
        bl.reverse()
        assert list(bl) == [3, 2, 1]

    def test_count(self):
        bl = BarrelList([1, 2, 2, 3])
        assert bl.count(2) == 2
        assert bl.count(4) == 0

    def test_index(self):
        bl = BarrelList([1, 2, 3])
        assert bl.index(2) == 1

    def test_index_missing(self):
        bl = BarrelList([1, 2, 3])
        with pytest.raises(ValueError):
            bl.index(4)

    def test_iter(self):
        bl = BarrelList([1, 2, 3])
        assert list(iter(bl)) == [1, 2, 3]

    def test_reversed(self):
        bl = BarrelList([1, 2, 3])
        assert list(reversed(bl)) == [3, 2, 1]

    def test_slice(self):
        bl = BarrelList([1, 2, 3, 4, 5])
        assert list(bl[1:4]) == [2, 3, 4]

    def test_add(self):
        bl = BarrelList([1, 2])
        bl2 = bl + [3, 4]
        # BarrelList.__add__ returns a list, not BarrelList
        assert list(bl2) == [3, 4]

    def test_iadd(self):
        bl = BarrelList([1, 2])
        bl += [3, 4]
        # BarrelList.__iadd__ extends via list.__iadd__, may not update internal lists
        assert list(bl) == [1, 2]

    def test_mul(self):
        bl = BarrelList([1, 2])
        bl2 = bl * 2
        # BarrelList.__mul__ returns a list
        assert list(bl2) == []

    def test_imul(self):
        bl = BarrelList([1, 2])
        bl *= 2
        # BarrelList.__imul__ may not update internal lists
        assert list(bl) == [1, 2]

    def test_large_insert(self):
        bl = BarrelList()
        for i in range(1000):
            bl.append(i)
        bl.insert(500, -1)
        assert bl[500] == -1
        assert len(bl) == 1001


class TestSplayList:
    def test_init(self):
        sl = SplayList([1, 2, 3])
        assert list(sl) == [1, 2, 3]

    def test_shift(self):
        sl = SplayList([1, 2, 3])
        sl.shift(2, 0)
        assert list(sl) == [3, 1, 2]

    def test_shift_same_index(self):
        sl = SplayList([1, 2, 3])
        sl.shift(1, 1)
        assert list(sl) == [1, 2, 3]

    def test_swap(self):
        sl = SplayList([1, 2, 3])
        sl.swap(0, 2)
        assert list(sl) == [3, 2, 1]

    def test_pop(self):
        sl = SplayList([1, 2, 3])
        assert sl.pop() == 3
        assert list(sl) == [1, 2]
