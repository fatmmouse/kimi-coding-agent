from boltons.timeutils import (
    dt_to_timestamp, isoparse, parse_timedelta,
    strpdate, daterange, decimal_relative_time, relative_time,
    ConstantTZInfo, LocalTZInfo, USTimeZone,
)


class TestDtToTimestamp:
    def test_basic(self):
        from datetime import datetime
        dt = datetime(2020, 1, 1)
        assert dt_to_timestamp(dt) == 1577836800.0


class TestStrpdate:
    def test_basic(self):
        from datetime import date
        assert strpdate('2020-01-01', '%Y-%m-%d') == date(2020, 1, 1)


class TestIsoparse:
    def test_basic(self):
        from datetime import datetime
        assert isoparse('2020-01-01T00:00:00') == datetime(2020, 1, 1, 0, 0, 0)


class TestParseTimedelta:
    def test_basic(self):
        from datetime import timedelta
        assert parse_timedelta('1 hour') == timedelta(hours=1)

    def test_invalid(self):
        from datetime import timedelta
        assert parse_timedelta('invalid') == timedelta(0)


class TestDaterange:
    def test_basic(self):
        from datetime import date
        dates = list(daterange(date(2020, 1, 1), date(2020, 1, 5)))
        assert len(dates) == 4
        assert dates[0] == date(2020, 1, 1)

    def test_inclusive(self):
        from datetime import date
        dates = list(daterange(date(2020, 1, 1), date(2020, 1, 5), inclusive=True))
        assert len(dates) == 5


class TestDecimalRelativeTime:
    def test_basic(self):
        from datetime import datetime
        d = datetime(2020, 1, 1)
        other = datetime(2020, 1, 2)
        assert decimal_relative_time(d, other) == (1.0, 'day')


class TestRelativeTime:
    def test_basic(self):
        from datetime import datetime
        d = datetime(2020, 1, 1)
        other = datetime(2020, 1, 2)
        assert relative_time(d, other) == '1 day ago'


class TestConstantTZInfo:
    def test_basic(self):
        from datetime import timedelta
        tz = ConstantTZInfo('TEST', offset=timedelta(hours=5))
        from datetime import datetime
        dt = datetime(2020, 1, 1, tzinfo=tz)
        assert dt.utcoffset().total_seconds() == 18000


class TestLocalTZInfo:
    def test_basic(self):
        tz = LocalTZInfo()
        from datetime import datetime
        dt = datetime(2020, 1, 1)
        assert tz.tzname(dt) is not None


class TestUSTimeZone:
    def test_est(self):
        tz = USTimeZone(-5, 'EST', 'EST', 'EDT')
        from datetime import datetime
        dt = datetime(2020, 1, 1, tzinfo=tz)
        assert dt.utcoffset().total_seconds() == -18000
