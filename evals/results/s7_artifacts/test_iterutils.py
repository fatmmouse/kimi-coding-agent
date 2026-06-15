import pytest
from boltons.iterutils import (
    is_iterable, is_scalar, is_collection,
    split, split_iter, lstrip, rstrip, strip,
    chunked, chunked_iter, chunk_ranges, pairwise, windowed,
    xfrange, frange, backoff, backoff_iter,
    bucketize, partition, unique, unique_iter, redundant,
    one, first, flatten, flatten_iter, same,
    get_path, research, soft_sorted, untyped_sorted,
    GUIDerator, SequentialGUIDerator,
)


class TestIsChecks:
    def test_is_iterable(self):
        assert is_iterable([1, 2, 3]) is True
        assert is_iterable('abc') is True
        assert is_iterable(42) is False

    def test_is_scalar(self):
        assert is_scalar(42) is True
        assert is_scalar(None) is True
        assert is_scalar([1, 2]) is False

    def test_is_collection(self):
        assert is_collection([1, 2, 3]) is True
        assert is_collection('abc') is False
        assert is_collection(42) is False


class TestSplit:
    def test_split_default(self):
        assert split([1, 2, None, 3, 4]) == [[1, 2], [3, 4]]

    def test_split_custom_sep(self):
        assert split([1, 2, 0, 3, 4], sep=0) == [[1, 2], [3, 4]]

    def test_split_maxsplit(self):
        assert split([1, 2, None, 3, 4, None, 5, 6], maxsplit=1) == [[1, 2], [3, 4, None, 5, 6]]

    def test_split_iter(self):
        assert list(split_iter([1, 2, None, 3, 4])) == [[1, 2], [3, 4]]


class TestStrip:
    def test_lstrip(self):
        assert lstrip([None, None, 1, 2, None]) == [1, 2, None]

    def test_rstrip(self):
        assert rstrip([None, 1, 2, None, None]) == [None, 1, 2]

    def test_strip(self):
        assert strip([None, None, 1, 2, None, None]) == [1, 2]


class TestChunked:
    def test_chunked(self):
        assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]

    def test_chunked_iter(self):
        assert list(chunked_iter([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]

    def test_chunk_ranges(self):
        assert list(chunk_ranges(10, 3)) == [(0, 3), (3, 6), (6, 9), (9, 10)]


class TestPairwise:
    def test_pairwise(self):
        assert list(pairwise([1, 2, 3])) == [(1, 2), (2, 3)]

    def test_pairwise_with_end(self):
        assert list(pairwise([1, 2, 3], end=0)) == [(1, 2), (2, 3), (3, 0)]


class TestWindowed:
    def test_windowed(self):
        assert list(windowed([1, 2, 3, 4], 2)) == [(1, 2), (2, 3), (3, 4)]

    def test_windowed_with_fill(self):
        assert list(windowed([1, 2, 3], 2, fill=0)) == [(1, 2), (2, 3), (3, 0)]


class TestXfrange:
    def test_xfrange(self):
        assert list(xfrange(5)) == [0.0, 1.0, 2.0, 3.0, 4.0]

    def test_xfrange_start_stop(self):
        assert list(xfrange(1, 5)) == [1.0, 2.0, 3.0, 4.0]

    def test_frange(self):
        assert list(frange(5)) == [0.0, 1.0, 2.0, 3.0, 4.0]


class TestBackoff:
    def test_backoff(self):
        assert list(backoff(1, 10, count=3)) == [1, 2, 4]

    def test_backoff_iter(self):
        assert list(backoff_iter(1, 10, count=3)) == [1, 2, 4]

    def test_backoff_with_jitter(self):
        result = list(backoff(1, 10, count=3, jitter=True))
        assert len(result) == 3
        assert all(r >= 0 for r in result)


class TestBucketize:
    def test_bucketize(self):
        result = bucketize([1, 2, 3, 4, 5], key=lambda x: x % 2)
        assert result[0] == [2, 4]
        assert result[1] == [1, 3, 5]

    def test_bucketize_value_transform(self):
        result = bucketize([1, 2, 3, 4], key=lambda x: x % 2, value_transform=lambda x: x * 2)
        assert result[0] == [4, 8]
        assert result[1] == [2, 6]


class TestPartition:
    def test_partition(self):
        truthy, falsy = partition([1, 2, 3, 4, 5], key=lambda x: x > 2)
        assert truthy == [3, 4, 5]
        assert falsy == [1, 2]


class TestUnique:
    def test_unique(self):
        assert unique([1, 2, 2, 3, 3, 3]) == [1, 2, 3]

    def test_unique_iter(self):
        assert list(unique_iter([1, 2, 2, 3, 3, 3])) == [1, 2, 3]

    def test_unique_key(self):
        assert unique(['a', 'A', 'b'], key=str.lower) == ['a', 'b']


class TestRedundant:
    def test_redundant(self):
        assert redundant([1, 2, 2, 3, 3, 3]) == [2, 3]

    def test_redundant_groups(self):
        assert redundant([1, 2, 2, 3, 3, 3], groups=True) == [[2, 2], [3, 3, 3]]


class TestOne:
    def test_one(self):
        assert one([42]) == 42

    def test_one_empty(self):
        assert one([]) is None

    def test_one_too_many(self):
        assert one([1, 2]) is None

    def test_one_default(self):
        assert one([], default=None) is None


class TestFirst:
    def test_first(self):
        assert first([1, 2, 3]) == 1

    def test_first_default(self):
        assert first([], default=None) is None

    def test_first_key(self):
        assert first([1, 2, 3, 4], key=lambda x: x > 2) == 3


class TestFlatten:
    def test_flatten(self):
        assert flatten([[1, 2], [3, 4]]) == [1, 2, 3, 4]

    def test_flatten_iter(self):
        assert list(flatten_iter([[1, 2], [3, 4]])) == [1, 2, 3, 4]

    def test_flatten_nested(self):
        assert flatten([[1, [2, 3]], [4]]) == [1, 2, 3, 4]


class TestSame:
    def test_same(self):
        assert same([1, 1, 1]) is True

    def test_same_false(self):
        assert same([1, 2, 1]) is False

    def test_same_empty(self):
        assert same([]) is True


class TestGetPath:
    def test_get_path_dict(self):
        assert get_path({'a': {'b': 1}}, ('a', 'b')) == 1

    def test_get_path_list(self):
        assert get_path([1, [2, 3]], (1, 1)) == 3

    def test_get_path_default(self):
        assert get_path({}, ('a',), default='missing') == 'missing'

    def test_get_path_missing(self):
        with pytest.raises(KeyError):
            get_path({}, ('a',))


class TestResearch:
    def test_research(self):
        result = list(research({'a': {'b': 1}}, query=lambda p, k, v: k == 'b'))
        assert len(result) == 1
        assert result[0] == (('a', 'b'), 1)


class TestSoftSorted:
    def test_soft_sorted(self):
        assert soft_sorted(['b', 'a', 'c'], first=['a']) == ['a', 'b', 'c']

    def test_untyped_sorted(self):
        assert untyped_sorted([3, '1', 2]) == [2, 3, '1']


class TestGUIDerator:
    def test_guiderator(self):
        g = GUIDerator()
        guid1 = next(g)
        guid2 = next(g)
        assert guid1 != guid2
        assert len(guid1) == 24

    def test_sequential_guiderator(self):
        g = SequentialGUIDerator()
        guid1 = next(g)
        guid2 = next(g)
        assert guid1 < guid2
