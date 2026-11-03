"""Tests for tiny-semver v0.2.0.

The v0.2.0 classes cover two correctness fixes and one missing capability:

  1. Pre-release identifiers sort per SemVer spec 11 (numeric below
     alphanumeric, numbers compared as numbers).
  2. Tilde/~= is the patch-level range, per PEP 440 and npm.
  3. Ranges: comma conjunctions, || disjunctions, resolution helpers.

Plus a construction bug fix: Version.raw was joined without the dot
separator, so every constructed version stringified as "100-alpha.2".
"""

import pytest

from tiny_semver_v2 import (
    Constraint,
    ConstraintSet,
    Version,
    bump_major,
    bump_minor,
    bump_patch,
    bump_prerelease,
    compare,
    filter_satisfying,
    find_max_satisfying,
    is_valid,
    parse,
    parse_constraint,
    parse_loose,
    parse_range,
    satisfies,
    sort,
)


SPEC_11_CHAIN = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
]


class TestPrereleaseOrdering:
    def test_full_spec_chain(self):
        """The canonical ordering from SemVer 2.0.0, section 11."""
        assert [str(v) for v in sort(SPEC_11_CHAIN)] == SPEC_11_CHAIN

    def test_release_outranks_all_prereleases(self):
        assert compare("1.0.0", "1.0.0-rc.1") > 0
        assert compare("1.0.0-rc.1", "1.0.0") < 0

    def test_numeric_identifiers_compare_numerically(self):
        """alpha.2 sorts below alpha.10, which string comparison gets wrong."""
        assert compare("1.0.0-alpha.2", "1.0.0-alpha.10") < 0
        assert parse("1.0.0-alpha.2") < parse("1.0.0-alpha.10")

    def test_numeric_below_alphanumeric(self):
        assert compare("1.0.0-1", "1.0.0-alpha") < 0
        assert compare("1.0.0-999", "1.0.0-alpha") < 0

    def test_leading_zeros_rejected_by_parser(self):
        """SemVer forbids numeric pre-release ids with leading zeros.

        The key builder still normalises them, so a hand-built Version
        compares numerically -- but the strict parser refuses the string,
        which is spec-correct.
        """
        assert parse("1.0.0-01") is None
        assert parse("1.0.0-1") is not None
        assert compare(Version(1, 0, 0, ("01",)), Version(1, 0, 0, ("1",))) == 0

    def test_shorter_prerelease_sorts_first(self):
        assert compare("1.0.0-alpha", "1.0.0-alpha.1") < 0

    def test_precedence_tuple_exposed(self):
        assert parse("1.2.3").precedence == (1, 2, 3, 1, ())

    def test_precedence_ignores_build_metadata(self):
        assert parse("1.0.0+a").precedence == parse("1.0.0+b").precedence

    def test_sorting_matches_expected_order(self):
        unsorted = ["1.0.0", "1.0.0-rc.1", "1.0.0-alpha.1", "2.0.0", "1.0.0-alpha"]
        assert [str(v) for v in sort(unsorted)] == [
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-rc.1",
            "1.0.0",
            "2.0.0",
        ]


class TestConstruction:
    def test_major_minor_patch_keep_dots(self):
        assert str(Version(1, 2, 3)) == "1.2.3"
        assert str(Version(10, 20, 30)) == "10.20.30"

    def test_prerelease_joined_with_dots(self):
        assert str(Version(1, 0, 0, ("alpha", "1"))) == "1.0.0-alpha.1"

    def test_build_metadata_appended(self):
        assert str(Version(1, 2, 3, (), ("build", "9"))) == "1.2.3+build.9"

    def test_parse_roundtrips_exactly(self):
        for text in ("1.2.3", "0.0.1", "1.0.0-alpha.1", "1.2.3+b.1", "1.0.0-rc.1+x"):
            assert str(parse(text)) == text

    def test_constructed_matches_parsed(self):
        assert Version(1, 0, 0, ("alpha", "2")) == parse("1.0.0-alpha.2")
        assert str(Version(1, 0, 0, ("alpha", "2"))) == "1.0.0-alpha.2"

    def test_big_version_numbers(self):
        assert str(Version(999, 888, 777)) == "999.888.777"

    def test_to_dict(self):
        d = parse("1.2.3-alpha.1+b").to_dict()
        assert d["major"] == 1
        assert d["prerelease"] == ["alpha", "1"]
        assert d["build"] == ["b"]

    def test_hash_and_equality_agree(self):
        a, b = parse("1.0.0-alpha.1"), parse("1.0.0-alpha.1")
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_build_metadata_ignored_in_equality(self):
        assert parse("1.0.0+a") == parse("1.0.0+b")


class TestTildeRange:
    def test_tilde_is_patch_level(self):
        """~=1.2.3 means >=1.2.3, ==1.2.* -- it must not accept 1.3.0."""
        assert satisfies("1.2.9", "~=1.2.3") is True
        assert satisfies("1.3.0", "~=1.2.3") is False

    def test_tilde_excludes_below_floor(self):
        assert satisfies("1.2.2", "~=1.2.3") is False

    def test_tilde_includes_floor(self):
        assert satisfies("1.2.3", "~=1.2.3") is True

    def test_bare_tilde_same_semantics(self):
        assert satisfies("1.3.0", "~1.2.3") is False
        assert satisfies("1.2.9", "~1.2.3") is True

    def test_tilde_from_zero_minor(self):
        assert satisfies("1.0.9", "~=1.0.0") is True
        assert satisfies("1.1.0", "~=1.0.0") is False

    def test_tilde_across_major_boundary(self):
        assert satisfies("2.0.0", "~=1.9.0") is False


class TestCaretRange:
    def test_caret_allows_minor_and_patch(self):
        assert satisfies("1.9.9", "^1.2.3") is True
        assert satisfies("1.2.9", "^1.2.3") is True

    def test_caret_blocks_next_major(self):
        assert satisfies("2.0.0", "^1.2.3") is False

    def test_caret_respects_floor(self):
        assert satisfies("1.2.2", "^1.2.3") is False

    def test_caret_zero_major_uses_minor_axis(self):
        assert satisfies("0.2.9", "^0.2.3") is True
        assert satisfies("0.3.0", "^0.2.3") is False

    def test_caret_zero_zero_is_narrow(self):
        assert satisfies("0.0.3", "^0.0.3") is True
        assert satisfies("0.0.4", "^0.0.3") is False


class TestBasicOperators:
    @pytest.mark.parametrize("version,expected", [
        ("1.0.0", True),
        ("0.9.9", False),
        ("2.0.0", True),
    ])
    def test_ge(self, version, expected):
        assert satisfies(version, ">=1.0.0") is expected

    def test_exact_equality(self):
        assert satisfies("2.0.0", "==2.0.0") is True
        assert satisfies("2.0.1", "==2.0.0") is False

    def test_inequality(self):
        assert satisfies("2.0.0", "!=2.0.0") is False
        assert satisfies("2.0.1", "!=2.0.0") is True

    def test_bare_version_is_equality(self):
        assert satisfies("1.2.3", "1.2.3") is True
        assert satisfies("1.2.4", "1.2.3") is False

    def test_lt_and_lte(self):
        assert satisfies("1.0.0", "<2.0.0") is True
        assert satisfies("2.0.0", "<=2.0.0") is True
        assert satisfies("2.0.1", "<=2.0.0") is False


class TestConstraintSet:
    def test_conjunction_requires_all_members(self):
        s = parse_range(">=1.2.0, <2.0.0")[0]
        assert isinstance(s, ConstraintSet)
        assert s.check(parse("1.5.0")) is True
        assert s.check(parse("2.5.0")) is False
        assert s.check(parse("1.0.0")) is False

    def test_conjunction_of_three(self):
        s = parse_range(">=1.0.0, <2.0.0, !=1.5.0")[0]
        assert s.check(parse("1.4.0")) is True
        assert s.check(parse("1.5.0")) is False

    def test_whitespace_tolerated(self):
        assert len(parse_range(">=1.0.0 ,   <2.0.0")[0]) == 2

    def test_len_and_iteration(self):
        s = parse_range(">=1.2.0, <2.0.0")[0]
        assert len(s) == 2
        assert [c.op for c in s] == [">=", "<"]

    def test_empty_set_matches_everything(self):
        s = parse_range("*")[0]
        assert len(s) == 0
        assert bool(s) is False
        assert s.check(parse("9.9.9")) is True

    def test_callable_with_string(self):
        s = parse_range(">=1.0.0")[0]
        assert s("1.5.0") is True
        assert s("0.5.0") is False

    def test_str_roundtrips(self):
        assert str(parse_range(">=1.2.0, <2.0.0")[0]) == ">=1.2.0, <2.0.0"

    def test_equality_and_hash(self):
        a = parse_range(">=1.2.0, <2.0.0")[0]
        b = parse_range(">=1.2.0, <2.0.0")[0]
        assert a == b
        assert hash(a) == hash(b)

    def test_invalid_version_fails_call(self):
        assert parse_range(">=1.0.0")[0]("not-a-version") is False


class TestRangeDisjunction:
    def test_two_alternatives(self):
        assert len(parse_range("^1.0.0 || ^2.0.0")) == 2

    def test_disjunction_matches_either_branch(self):
        assert satisfies("1.5.0", "^1.0.0 || ^2.0.0") is True
        assert satisfies("2.5.0", "^1.0.0 || ^2.0.0") is True

    def test_disjunction_rejects_other_branches(self):
        assert satisfies("3.5.0", "^1.0.0 || ^2.0.0") is False
        assert satisfies("0.9.0", "^1.0.0 || ^2.0.0") is False

    def test_three_alternatives(self):
        assert len(parse_range("^1.0.0 || ^2.0.0 || ^3.0.0")) == 3

    def test_conjunction_inside_disjunction(self):
        assert satisfies("1.5.0", ">=1.0.0, <2.0.0 || >=3.0.0") is True
        assert satisfies("2.5.0", ">=1.0.0, <2.0.0 || >=3.0.0") is False

    def test_empty_spec_matches_anything(self):
        assert satisfies("1.0.0", "") is True
        assert satisfies("9.9.9", "   ") is True

    def test_conjunction_through_satisfies(self):
        assert satisfies("1.5.0", ">=1.2.0, <2.0.0") is True
        assert satisfies("2.5.0", ">=1.2.0, <2.0.0") is False

    def test_satisfies_accepts_constraint_set(self):
        s = parse_range(">=1.2.0, <2.0.0")[0]
        assert satisfies("1.5.0", s) is True
        assert satisfies("2.5.0", s) is False

    def test_satisfies_accepts_constraint_object(self):
        c = parse_constraint(">=1.2.0")
        assert satisfies("1.5.0", c) is True
        assert satisfies("1.1.0", c) is False

    def test_invalid_version_returns_false(self):
        assert satisfies("garbage", ">=1.0.0") is False


class TestResolution:
    def test_filter_returns_matches_in_order(self):
        out = filter_satisfying(["1.0.0", "1.4.2", "2.0.0"], "^1.0.0")
        assert [str(v) for v in out] == ["1.0.0", "1.4.2"]

    def test_filter_drops_unparseable_entries(self):
        out = filter_satisfying(["1.0.0", "junk", "1.4.2"], "^1.0.0")
        assert [str(v) for v in out] == ["1.0.0", "1.4.2"]

    def test_filter_with_disjunction(self):
        out = filter_satisfying(["1.0.0", "2.0.0", "3.0.0"], "^1.0.0 || ^2.0.0")
        assert [str(v) for v in out] == ["1.0.0", "2.0.0"]

    def test_filter_empty_result(self):
        assert filter_satisfying(["3.0.0"], "^1.0.0") == []

    def test_filter_accepts_parsed_versions(self):
        assert len(filter_satisfying([parse("1.0.0"), parse("2.0.0")], "^1.0.0")) == 1

    def test_max_returns_highest_match(self):
        assert str(find_max_satisfying(["1.0.0", "1.4.2", "2.0.0"], "^1.0.0")) == "1.4.2"

    def test_max_orders_numerically_not_lexically(self):
        assert str(find_max_satisfying(["1.9.0", "1.10.0"], "^1.0.0")) == "1.10.0"

    def test_max_returns_none_when_nothing_matches(self):
        assert find_max_satisfying(["3.0.0"], "^1.0.0") is None

    def test_max_on_empty_input(self):
        assert find_max_satisfying([], "^1.0.0") is None

    def test_max_with_open_range(self):
        assert str(find_max_satisfying(["1.0.0", "5.0.0"], ">=0.0.0")) == "5.0.0"


class TestPrereleaseBump:
    def test_increments_trailing_number(self):
        assert str(bump_prerelease("1.0.0-alpha.1")) == "1.0.0-alpha.2"

    def test_double_digit_increment(self):
        assert str(bump_prerelease("1.0.0-alpha.9")) == "1.0.0-alpha.10"

    def test_opens_numeric_slot_after_tag(self):
        assert str(bump_prerelease("1.0.0-alpha")) == "1.0.0-alpha.0"

    def test_opens_prerelease_cycle(self):
        assert str(bump_prerelease("1.0.0")) == "1.0.0-0"

    def test_stable_drops_trailing_number(self):
        assert str(parse("1.0.0-rc.1").bump_prerelease(stable=True)) == "1.0.0"

    def test_stable_on_unnumbered_tag_releases(self):
        """stable=True always means the plain release, tag or not."""
        assert str(parse("1.0.0-alpha").bump_prerelease(stable=True)) == "1.0.0"

    def test_stable_on_release_is_noop(self):
        assert str(parse("1.2.3").bump_prerelease(stable=True)) == "1.2.3"

    def test_bump_release_drops_tag(self):
        assert str(parse("1.0.0-rc.1").bump_release()) == "1.0.0"

    def test_bump_release_on_release_is_noop(self):
        assert str(parse("1.2.3").bump_release()) == "1.2.3"

    def test_bump_sequence_reaches_release(self):
        v = parse("1.0.0-rc.1").bump_prerelease().bump_prerelease()
        assert str(v) == "1.0.0-rc.3"
        assert str(v.bump_release()) == "1.0.0"


class TestBump:
    def test_major(self):
        assert str(bump_major("1.2.3")) == "2.0.0"

    def test_minor(self):
        assert str(bump_minor("1.2.3")) == "1.3.0"

    def test_patch(self):
        assert str(bump_patch("1.2.3")) == "1.2.4"

    def test_major_drops_prerelease(self):
        assert str(bump_major("1.2.3-rc.1")) == "2.0.0"

    def test_bump_of_parsed_object(self):
        assert str(bump_patch(parse("1.2.3"))) == "1.2.4"


class TestCompat:
    def test_same_major_is_compatible(self):
        assert parse("1.0.0").is_compatible_with(parse("1.9.9")) is True

    def test_different_major_is_not(self):
        assert parse("1.0.0").is_compatible_with(parse("2.0.0")) is False

    def test_older_is_not_compatible_forward(self):
        assert parse("1.5.0").is_compatible_with(parse("1.2.0")) is False

    def test_zero_major_uses_minor_axis(self):
        assert parse("0.2.0").is_compatible_with(parse("0.2.9")) is True
        assert parse("0.2.0").is_compatible_with(parse("0.3.0")) is False


class TestBackwardsCompatibility:
    def test_parse_basic(self):
        v = parse("1.2.3")
        assert (v.major, v.minor, v.patch) == (1, 2, 3)

    def test_parse_prerelease(self):
        assert parse("1.0.0-alpha.1.beta.2").prerelease == ("alpha", "1", "beta", "2")

    def test_parse_build(self):
        assert parse("1.0.0+build.123").build == ("build", "123")

    def test_parse_rejects_garbage(self):
        assert parse("not-a-version") is None
        assert parse("") is None
        assert parse(None) is None

    def test_is_valid(self):
        assert is_valid("1.0.0") is True
        assert is_valid("1.0") is False

    def test_compare_variants(self):
        assert compare(parse("1.0.0"), "2.0.0") == -1
        assert compare("1.0.0", parse("1.0.0")) == 0

    def test_loose_parsing(self):
        assert parse_loose("v1.2.3").major == 1

    def test_constraint_repr_and_str(self):
        c = parse_constraint(">=1.2.3")
        assert isinstance(c, Constraint)
        assert str(c) == ">=1.2.3"
        assert "Constraint" in repr(c)

    def test_constraint_equality(self):
        assert parse_constraint(">=1.2.3") == parse_constraint(">=1.2.3")
        assert parse_constraint(">=1.2.3") != parse_constraint(">1.2.3")

    def test_constraint_hashable(self):
        assert len({parse_constraint(">=1.2.3"), parse_constraint(">=1.2.3")}) == 1

    def test_version_satisfies_constraint(self):
        assert parse("1.5.0").satisfies_constraint(parse_constraint(">=1.0.0")) is True

    def test_sort_drops_invalid(self):
        assert len(sort(["1.0.0", "junk", "2.0.0"])) == 2
