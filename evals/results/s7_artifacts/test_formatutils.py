from boltons.formatutils import (
    construct_format_field_str, split_format_str,
    infer_positional_format_args, get_format_args, tokenize_format_str,
    BaseFormatField, DeferredValue,
)
import pytest


class TestConstructFormatFieldStr:
    def test_basic(self):
        assert construct_format_field_str('name', '', None) == '{name}'

    def test_with_conversion(self):
        assert construct_format_field_str('name', '', 'r') == '{name!r}'

    def test_with_spec(self):
        assert construct_format_field_str('name', '>10', None) == '{name:>10}'


class TestSplitFormatStr:
    def test_basic(self):
        assert split_format_str('Hello {name}') == [('Hello ', '{name}')]

    def test_no_fields(self):
        assert split_format_str('Hello') == [('Hello', None)]


class TestInferPositionalFormatArgs:
    def test_basic(self):
        assert infer_positional_format_args('{} {}') == '{0} {1}'

    def test_mixed(self):
        assert infer_positional_format_args('{} {name}') == '{0} {name}'


class TestGetFormatArgs:
    def test_named(self):
        args, kwargs = get_format_args('{name}')
        assert args == []
        assert kwargs == [('name', str)]

    def test_positional_raises(self):
        with pytest.raises(ValueError):
            get_format_args('{}')


class TestTokenizeFormatStr:
    def test_basic(self):
        tokens = list(tokenize_format_str('Hello {name}'))
        assert tokens[0] == 'Hello '
        assert isinstance(tokens[1], BaseFormatField)


class TestBaseFormatField:
    def test_init(self):
        field = BaseFormatField('name', '>10', 'r')
        assert field.fname == 'name'
        assert field.fspec == '>10'
        assert field.conv == 'r'

    def test_repr(self):
        field = BaseFormatField('name', '>10', 'r')
        assert repr(field) == "BaseFormatField('name', '>10', 'r')"


class TestDeferredValue:
    def test_basic(self):
        def factory():
            return 42
        dv = DeferredValue(factory)
        assert dv.get_value() == 42

    def test_str(self):
        def factory():
            return 42
        dv = DeferredValue(factory)
        assert str(dv) == '42'
