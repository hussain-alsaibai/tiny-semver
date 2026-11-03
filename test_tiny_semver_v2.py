"""Tests for tiny-semver."""
import pytest
from tiny_semver_v2 import (
    parse,
    parse_loose,
    is_valid,
    compare,
    match,
    sort,
    satisfies,
    bump_major,
    bump_minor,
    bump_patch,
    bump_prerelease,
    Version,
    Constraint,
)


class TestParse:
    def test_basic(self):
        v = parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3
        assert not v.is_prerelease

    def test_prerelease(self):
        v = parse("1.0.0-alpha")
        assert v.prerelease == ("alpha",)
        assert v.is_prerelease

    def test_prerelease_multi(self):
        v = parse("1.0.0-alpha.1.beta.2")
        assert v.prerelease == ("alpha", "1", "beta", "2")

    def test_build_metadata(self):
        v = parse("1.0.0+build.123")
        assert v.build == ("build", "123")

    def test_invalid(self):
        assert parse("not-a-version") is None
        assert parse("") is None
        assert parse("1.2") is None

    def test_v_prefix(self):
        v = parse_loose("v1.2.3")
        assert v.major == 1


class TestCompare:
    def test_basic(self):
        assert compare("2.0.0", "1.0.0") == 1
        assert compare("1.0.0", "2.0.0") == -1
        assert compare("1.0.0", "1.0.0") == 0

    def test_prerelease_less_than_release(self):
        assert compare("2.0.0-alpha", "2.0.0") == -1
        assert compare("2.0.0-alpha", "2.0.0-beta") == -1

    def test_sort(self):
        versions = ["1.10.0", "1.2.0", "2.0.0-alpha", "1.2.0+build", "2.0.0"]
        sorted_v = sort(versions)
        assert [str(v) for v in sorted_v] == ["1.2.0", "1.2.0+build", "1.10.0", "2.0.0-alpha", "2.0.0"]


class TestConstraints:
    def test_gte(self):
        assert satisfies("1.2.0", ">=1.0.0")
        assert satisfies("1.0.0", ">=1.0.0")
        assert not satisfies("0.9.0", ">=1.0.0")

    def test_caret(self):
        assert satisfies("1.9.9", "^1.2.3")
        assert not satisfies("2.0.0", "^1.2.3")
        assert not satisfies("0.9.0", "^1.2.3")

    def test_tilde(self):
        # PEP 440: ~=1.2.3 means >=1.2.3, ==1.2.* (patch-level).
        # Corrected in v0.2.0; the v0.1.0 assertion here claimed 1.3.0
        # was in range, contradicting PEP 440 and npm.
        assert satisfies("1.2.9", "~=1.2.3")
        assert not satisfies("1.3.0", "~=1.2.3")   # next minor is out
        assert not satisfies("2.0.0", "~=1.2.3")

    def test_exact(self):
        assert satisfies("1.2.3", "==1.2.3")
        assert not satisfies("1.2.4", "==1.2.3")

    def test_not_equal(self):
        assert satisfies("1.2.4", "!=1.2.3")
        assert not satisfies("1.2.3", "!=1.2.3")


class TestBump:
    def test_major(self):
        assert bump_major("1.2.3") == Version(2, 0, 0)

    def test_minor(self):
        assert bump_minor("1.2.3") == Version(1, 3, 0)

    def test_patch(self):
        assert bump_patch("1.2.3") == Version(1, 2, 4)


class TestLoose:
    def test_rc_version(self):
        v = parse_loose("1.2.3rc1")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_invalid_becomes_zero(self):
        v = parse_loose("not-a-version")
        assert v.major == 0
