import pytest
from boltons.strutils import (
    camel2under,
    under2camel,
    slugify,
    split_punct_ws,
    unit_len,
    ordinalize,
    cardinalize,
    pluralize,
    singularize,
    strip_ansi,
    asciify,
    indent,
    is_uuid,
    parse_int_list,
    format_int_list,
    complement_int_list,
    int_ranges_from_int_list,
    gzip_bytes,
    gunzip_bytes,
    html2text,
    escape_shell_args,
    args2sh,
    removeprefix,
    human_readable_list,
)


class TestCamelUnder:
    def test_camel2under_basic(self):
        assert camel2under("FooBar") == "foo_bar"
        assert camel2under("fooBar") == "foo_bar"

    def test_under2camel_basic(self):
        assert under2camel("foo_bar") == "FooBar"

    def test_roundtrip(self):
        assert under2camel(camel2under("FooBarBaz")) == "FooBarBaz"


class TestSlugify:
    def test_slugify_basic(self):
        assert slugify("Hello World") == "hello_world"

    def test_slugify_unicode(self):
        result = slugify("Café", ascii=True)
        assert result == b"cafe"

    def test_slugify_empty(self):
        assert slugify("") == ""


class TestSplitPunctWs:
    def test_basic(self):
        assert split_punct_ws("Hello, world!") == ["Hello", "world"]

    def test_empty(self):
        assert split_punct_ws("") == []


class TestUnitLen:
    def test_bytes(self):
        assert unit_len(b"abc") == "3 items"

    def test_list(self):
        assert unit_len([1, 2, 3]) == "3 items"

    def test_empty(self):
        assert unit_len([]) == "No items"


class TestOrdinalize:
    def test_basic(self):
        assert ordinalize(1) == "1st"
        assert ordinalize(2) == "2nd"
        assert ordinalize(3) == "3rd"
        assert ordinalize(4) == "4th"

    def test_teens(self):
        assert ordinalize(11) == "11th"
        assert ordinalize(12) == "12th"
        assert ordinalize(13) == "13th"

    def test_negative(self):
        assert ordinalize(-1) == "-1st"


class TestCardinalize:
    def test_basic(self):
        assert cardinalize("cat", 1) == "cat"
        assert cardinalize("cat", 2) == "cats"

    def test_override(self):
        assert cardinalize("person", 2) == "people"


class TestPluralize:
    def test_basic(self):
        assert pluralize("cat") == "cats"
        assert pluralize("cat") == "cats"

    def test_irregular(self):
        assert pluralize("person") == "people"


class TestSingularize:
    def test_basic(self):
        assert singularize("cats") == "cat"
        assert singularize("cat") == "cat"

    def test_irregular(self):
        assert singularize("people") == "person"


class TestStripAnsi:
    def test_basic(self):
        assert strip_ansi("\x1b[31mred\x1b[0m") == "red"

    def test_no_ansi(self):
        assert strip_ansi("hello") == "hello"


class TestAsciify:
    def test_basic(self):
        assert asciify("café") == b"cafe"

    def test_already_ascii(self):
        assert asciify("hello") == b"hello"


class TestIndent:
    def test_basic(self):
        assert indent("hello\nworld", "  ") == "  hello\n  world"

    def test_no_newline(self):
        assert indent("hello", "  ") == "  hello"


class TestIsUuid:
    def test_valid(self):
        assert is_uuid("e682ccca-5a4c-4ef2-9711-73f9ad1e15ea")

    def test_invalid(self):
        assert not is_uuid("not-a-uuid")

    def test_uppercase(self):
        assert is_uuid("E682CCCA-5A4C-4EF2-9711-73F9AD1E15EA")

    def test_version1(self):
        assert is_uuid("0221f0d9-d4b9-11e5-a478-10ddb1c2feb9", version=1)


class TestIntList:
    def test_parse_int_list(self):
        assert parse_int_list("1,3,5-7") == [1, 3, 5, 6, 7]

    def test_format_int_list(self):
        assert format_int_list([1, 3, 5, 6, 7]) == "1,3,5-7"

    def test_complement_int_list(self):
        assert complement_int_list("1,3,5-7", range_start=1, range_end=10) == "2,4,8-9"

    def test_int_ranges_from_int_list(self):
        assert int_ranges_from_int_list("1,3,5-7") == ((1, 1), (3, 3), (5, 7))

    def test_parse_int_list_empty(self):
        assert parse_int_list("") == []

    def test_format_int_list_empty(self):
        assert format_int_list([]) == ""


class TestGzip:
    def test_roundtrip(self):
        data = b"hello world"
        compressed = gzip_bytes(data)
        assert gunzip_bytes(compressed) == data

    def test_gunzip_empty(self):
        with pytest.raises(Exception):
            gunzip_bytes(b"not gzipped")


class TestHtml2Text:
    def test_basic(self):
        assert html2text("<p>hello</p>") == "hello"

    def test_empty(self):
        assert html2text("") == ""


class TestEscapeShellArgs:
    def test_basic(self):
        assert escape_shell_args(["echo", "hello world"]) == "echo 'hello world'"

    def test_args2sh(self):
        assert args2sh(["echo", "hello world"]) == "echo 'hello world'"


class TestParseTimedelta:
    def test_basic(self):
        from boltons.timeutils import parse_timedelta
        td = parse_timedelta("1 day")
        assert td.days == 1

    def test_invalid(self):
        from datetime import timedelta
        from boltons.timeutils import parse_timedelta
        result = parse_timedelta("not a time")
        assert result == timedelta(0)


class TestRemoveprefix:
    def test_basic(self):
        assert removeprefix("foobar", "foo") == "bar"

    def test_no_prefix(self):
        assert removeprefix("foobar", "baz") == "foobar"

    def test_empty_prefix(self):
        assert removeprefix("foobar", "") == "foobar"


class TestHumanReadableList:
    def test_empty(self):
        assert human_readable_list([]) == ""

    def test_one(self):
        assert human_readable_list(["apple"]) == "apple"

    def test_two(self):
        assert human_readable_list(["apple", "banana"]) == "apple and banana"

    def test_three_oxford(self):
        assert human_readable_list(["apple", "banana", "cherry"]) == "apple, banana, and cherry"

    def test_three_no_oxford(self):
        assert human_readable_list(["apple", "banana", "cherry"], oxford=False) == "apple, banana and cherry"
