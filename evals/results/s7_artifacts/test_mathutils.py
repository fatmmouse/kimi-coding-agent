import math
import pytest
from boltons.mathutils import clamp, ceil, floor, Bits


class TestClamp:
    def test_within_range(self):
        assert clamp(5, 0, 10) == 5

    def test_below_lower(self):
        assert clamp(-5, 0, 10) == 0

    def test_above_upper(self):
        assert clamp(15, 0, 10) == 10

    def test_defaults(self):
        assert clamp(5) == 5
        assert clamp(float('-inf')) == float('-inf')
        assert clamp(float('inf')) == float('inf')

    def test_equal_bounds(self):
        assert clamp(5, 5, 5) == 5


class TestCeil:
    def test_no_options(self):
        assert ceil(5.1) == 6

    def test_with_options(self):
        assert ceil(3.5, options=[1.5, 2.5, 4, 6]) == 4

    def test_exact_match(self):
        assert ceil(4, options=[1.5, 4, 6]) == 4

    def test_no_valid_option(self):
        with pytest.raises(ValueError):
            ceil(5, options=[1, 2])


class TestFloor:
    def test_no_options(self):
        assert floor(5.9) == 5

    def test_with_options(self):
        assert floor(3.5, options=[1.5, 2.5, 4, 6]) == 2.5

    def test_exact_match(self):
        assert floor(4, options=[1.5, 4, 6]) == 4

    def test_no_valid_option(self):
        with pytest.raises(ValueError):
            floor(5, options=[10, 20])


class TestBits:
    def test_init(self):
        b = Bits(0b1010)
        assert b.val == 0b1010

    def test_bool(self):
        assert bool(Bits(0b1010)) is True
        assert bool(Bits(0)) is True

    def test_iter(self):
        b = Bits(0b1010)
        assert list(b) == [1, 0, 1, 0]

    def test_len(self):
        assert len(Bits(0b1010)) == 4

    def test_getitem(self):
        b = Bits(0b1010)
        assert b[0] == 1
        assert b[1] == 0
        assert b[2] == 1
        assert b[3] == 0

    def test_eq(self):
        assert Bits(0b1010) == Bits(0b1010)
        assert Bits(0b1010) != Bits(0b0101)

    def test_hash(self):
        assert hash(Bits(0b1010)) == hash(Bits(0b1010))

    def test_repr(self):
        assert repr(Bits(0b1010)) == "Bits('1010')"

    def test_as_int(self):
        assert Bits(0b1010).as_int() == 0b1010

    def test_as_bin(self):
        assert Bits(0b1010).as_bin() == '1010'

    def test_as_hex(self):
        assert Bits(0b1010).as_hex() == '0A'

    def test_as_list(self):
        assert Bits(0b1010).as_list() == [True, False, True, False]

    def test_as_bytes(self):
        assert Bits(0b1010).as_bytes() == b'\x0a'

    def test_and(self):
        b1 = Bits(0b1010)
        b2 = Bits(0b1100)
        assert b1 & b2 == Bits(0b1000)

    def test_or(self):
        b1 = Bits(0b1010)
        b2 = Bits(0b1100)
        assert b1 | b2 == Bits(0b1110)

    def test_lshift(self):
        b = Bits(0b1010)
        assert b << 1 == Bits(0b10100)

    def test_rshift(self):
        b = Bits(0b1010)
        assert b >> 1 == Bits(0b0101)

    def test_from_list(self):
        b = Bits.from_list([1, 0, 1, 0])
        assert b == Bits(0b1010)

    def test_from_bin(self):
        b = Bits.from_bin('1010')
        assert b == Bits(0b1010)

    def test_from_hex(self):
        b = Bits.from_hex('0A')
        assert b == Bits(0b1010, 8)

    def test_from_int(self):
        b = Bits.from_int(0b1010)
        assert b == Bits(0b1010)

    def test_from_bytes(self):
        b = Bits.from_bytes(b'\x0a')
        assert b == Bits(0b1010, 8)
