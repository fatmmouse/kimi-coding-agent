from boltons.statsutils import Stats, describe, format_histogram_counts


class TestDescribe:
    def test_basic(self):
        result = describe([1, 2, 3, 4])
        assert isinstance(result, dict)
        assert result['mean'] == 2.5
        assert result['count'] == 4

    def test_empty(self):
        result = describe([])
        assert isinstance(result, dict)
        assert result['count'] == 0.0


class TestStats:
    def test_mean(self):
        s = Stats([1, 2, 3, 4])
        assert s.mean == 2.5

    def test_median(self):
        s = Stats([1, 2, 3, 4])
        assert s.median == 2.5

    def test_count(self):
        s = Stats([1, 2, 3, 4])
        assert s.count == 4

    def test_min(self):
        s = Stats([1, 2, 3, 4])
        assert s.min == 1

    def test_max(self):
        s = Stats([1, 2, 3, 4])
        assert s.max == 4

    def test_std_dev(self):
        s = Stats([2, 4, 4, 4, 5, 5, 7, 9])
        assert round(s.std_dev, 2) == 2.0

    def test_variance(self):
        s = Stats([2, 4, 4, 4, 5, 5, 7, 9])
        assert round(s.variance, 2) == 4.0

    def test_empty(self):
        s = Stats([])
        assert s.mean == 0.0
        assert s.count == 0

    def test_len(self):
        s = Stats([1, 2, 3])
        assert len(s) == 3

    def test_iter(self):
        s = Stats([1, 2, 3])
        assert list(s) == [1, 2, 3]

    def test_get_quantile(self):
        s = Stats([1, 2, 3, 4])
        assert s.get_quantile(0.5) == 2.5

    def test_get_zscore(self):
        s = Stats([1, 2, 3, 4])
        z = s.get_zscore(4)
        assert round(z, 2) == 1.34

    def test_trim_relative(self):
        s = Stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        s.trim_relative(0.2)
        assert s.count == 6

    def test_histogram_counts(self):
        s = Stats([1, 2, 3, 4, 5])
        counts = s.get_histogram_counts(bins=3)
        assert len(counts) == 3

    def test_format_histogram(self):
        s = Stats([1, 2, 3, 4, 5])
        hist = s.format_histogram(bins=3)
        assert isinstance(hist, str)
        assert '#' in hist

    def test_clear_cache(self):
        s = Stats([1, 2, 3, 4])
        _ = s.mean
        s.clear_cache()
        assert s.mean == 2.5

    def test_iqr(self):
        s = Stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert s.iqr == 4.5

    def test_trimean(self):
        s = Stats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        assert s.trimean == 5.5

    def test_median_abs_dev(self):
        s = Stats([1, 2, 3, 4, 5])
        assert s.median_abs_dev == 1.0

    def test_rel_std_dev(self):
        s = Stats([2, 4, 4, 4, 5, 5, 7, 9])
        assert round(s.rel_std_dev, 2) == 0.4

    def test_skewness(self):
        s = Stats([1, 2, 3, 4, 5])
        assert round(s.skewness, 2) == 0.0

    def test_kurtosis(self):
        s = Stats([1, 2, 3, 4, 5])
        assert round(s.kurtosis, 2) == 2.12

    def test_pearson_type(self):
        s = Stats([1, 2, 3, 4, 5])
        assert s.pearson_type in (1, 2, 3, 4, 5, 6, 7)


class TestFormatHistogramCounts:
    def test_basic(self):
        counts = [(1, 5), (2, 3), (3, 8)]
        hist = format_histogram_counts(counts, width=40)
        assert isinstance(hist, str)
        assert '#' in hist
