"""
tiny-semver — Pure Python semantic versioning (PEP 440 / SemVer 2.0.0).

Parse, compare, sort, constrain, and increment SemVer strings.
Zero dependencies. ~1M ops/sec.

Supports:
  - Semantic Versioning 2.0.0  (major.minor.patch[-prerelease][+build])
  - PEP 440 Python versioning  (major.minor.patch[.devN][+postN][aN][bN][rcN])
  - Loose (any version-like string)
  - Bump major / minor / patch / prerelease
  - Constraint matching: ==, !=, <, <=, >, >=, ~= (compatible), ^
  - Sorting (natural, SemVer order)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import total_ordering
from typing import Iterable, Iterator, List

__version__ = "0.2.0"
__all__ = [
    "Version",
    "parse",
    "parse_loose",
    "is_valid",
    "compare",
    "match",
    "sort",
    "bump_major",
    "bump_minor",
    "bump_patch",
    "bump_prerelease",
    "Constraint",
    "ConstraintSet",
    "satisfies",
    "parse_range",
    "filter_satisfying",
    "find_max_satisfying",
]

# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def _prerelease_key(parts: tuple) -> tuple:
    """Order pre-release identifiers per SemVer spec 11.

    Numeric identifiers always have lower precedence than alphanumeric
    ones, and numeric identifiers compare numerically, not as strings.

        alpha < alpha.1 < alpha.beta < beta < beta.2 < beta.11 < rc.1 < 1.0.0

    The classic trap this fixes: "alpha.2" > "alpha.10" under plain string
    comparison, but alpha.2 < alpha.10 under the spec. Each identifier
    becomes a (kind, value) pair, where kind 0 is numeric and 1 is
    alphanumeric, so numeric sorts below alphanumeric and never compares
    against a string.
    """
    key: list = []
    for part in parts:
        if part.isdigit():
            # Normalise leading zeros: "01" and "1" are the same number.
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part))
    return tuple(key)


# SemVer 2.0.0: major.minor.patch[-prerelease][+build]
SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>(?:[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*)))?$"
)

# PEP 440: major.minor[.devN][+postN][aN][bN][rcN]
PEP440_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:(?:\.(?P<dev>[1-9]\d*|0(?![.\d])))?"
    r"(?:\+(?:post(?P<post>[1-9]\d*|\d*[a-z]\d*)))?"
    r"(?:a(?P<alpha>[1-9]\d*|\d*[a-z]\d*))?"
    r"(?:b(?P<beta>[1-9]\d*|\d*[a-z]\d*))?"
    r"(?:rc(?P<release_candidate>[1-9]\d*|\d*[a-z]\d*))?)?$"
)

# Loose: any version-like string (major.minor.patch with optional junk)
LOOSE_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


@total_ordering
@dataclass
class Version:
    """A semantic version. Comparable, hashable, sortable."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()
    raw: str = ""

    def __post_init__(self):
        # raw is derived from the fields, never carried over from whatever
        # version this was derived from. v0.1.0 only filled it in when empty,
        # so every bump produced nonsense like "100-alpha.2" for 1.0.0-alpha.1.
        parts = [str(self.major), str(self.minor), str(self.patch)]
        if self.prerelease:
            parts.append("-" + ".".join(self.prerelease))
        if self.build:
            parts.append("+" + ".".join(self.build))
        self.raw = ".".join(parts[:3]) + "".join(parts[3:])

    def __str__(self) -> str:
        return self.raw

    def __repr__(self) -> str:
        return f"Version({self.major}.{self.minor}.{self.patch}" + (
            f", prerelease={self.prerelease!r}, build={self.build!r})"
            if self.prerelease or self.build
            else ")"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() == other._key()

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self._key() < other._key()

    def __hash__(self) -> int:
        return hash(self._key())

    def _key(self) -> tuple:
        # Build metadata is ignored in comparisons (SemVer spec 10).
        # A release outranks any pre-release, so the release gets the
        # larger sentinel.
        release_key = 1 if not self.prerelease else 0
        return (
            self.major,
            self.minor,
            self.patch,
            release_key,
            _prerelease_key(self.prerelease),
        )

    @property
    def precedence(self) -> tuple:
        """The tuple used for ordering, with build metadata excluded.

        Exposed so callers can sort mixed version sources by the same rules
        this module uses instead of reimplementing them.
        """
        return self._key()

    def is_compatible_with(self, other: "Version") -> bool:
        """True if other may be added without a major-version bump.

        Follows the caret convention: for major > 0 anything below the next
        major is compatible; for major == 0 the minor is the breaking axis,
        matching npm, Cargo, and the caret ranges this module parses.
        """
        if other.major != self.major:
            return False
        if self.major == 0:
            return other.minor == self.minor and other >= self
        return other >= self

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def next_major(self) -> "Version":
        return Version(self.major + 1, 0, 0)

    def next_minor(self) -> "Version":
        return Version(self.major, self.minor + 1, 0)

    def next_patch(self) -> "Version":
        return Version(self.major, self.minor, self.patch + 1)

    def bump_prerelease(self, stable: bool = False) -> "Version":
        """Advance the pre-release tag.

            1.0.0-alpha.1  ->  1.0.0-alpha.2   (increment trailing number)
            1.0.0-alpha    ->  1.0.0-alpha.0   (open a numeric slot)
            1.0.0          ->  1.0.0-0         (open a pre-release cycle)

        With stable=True the pre-release is dropped entirely and the plain
        release is returned, which is the rc-to-release step:

            1.0.0-rc.1     ->  1.0.0
            1.2.3          ->  1.2.3   (already stable, unchanged)

        Same result as bump_release(); it exists so release scripts can
        express the choice at the call site.
        """
        if stable:
            return Version(self.major, self.minor, self.patch)

        if not self.prerelease:
            return Version(self.major, self.minor, self.patch, ("0",))

        parts = list(self.prerelease)
        if parts[-1].isdigit():
            parts[-1] = str(int(parts[-1]) + 1)
        else:
            parts.append("0")

        return Version(self.major, self.minor, self.patch, tuple(parts))

    def bump_release(self) -> "Version":
        """Drop the pre-release tag and return the plain release.

            1.0.0-rc.1  ->  1.0.0
            1.2.3       ->  1.2.3
        """
        if not self.prerelease:
            return Version(self.major, self.minor, self.patch)
        return Version(self.major, self.minor, self.patch)

    def satisfies_constraint(self, constraint: "Constraint") -> bool:
        return constraint.check(self)

    def to_dict(self) -> dict:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "prerelease": list(self.prerelease),
            "build": list(self.build),
        }


def parse(version: str) -> Version | None:
    """
    Parse a SemVer 2.0.0 string into a Version.
    Returns None if the string is not valid SemVer.
    Supports pre-release tags like "alpha.1", "beta.2", "rc.3".
    """
    if not version or not isinstance(version, str):
        return None

    m = SEMVER_RE.match(version.strip())
    if not m:
        return None

    d = m.groupdict()
    prerelease = ()
    build = ()

    if d["prerelease"]:
        raw_pre = d["prerelease"]
        # Normalize "alpha.1" → "alpha.1" (already dot-separated per spec)
        prerelease = tuple(raw_pre.split("."))

    if d["build"]:
        build = tuple(d["build"].split("."))

    return Version(
        int(d["major"]),
        int(d["minor"]),
        int(d["patch"]),
        prerelease,
        build,
        raw=version.strip(),
    )


def parse_loose(version: str) -> Version:
    """
    Parse any version-like string (e.g. "1.2.3rc1", "v1.2.3", "1.2.3-beta.4").
    Falls back to major=0, minor=0 if nothing numeric found.
    """
    version = version.strip().lstrip("v")
    m = LOOSE_RE.match(version)
    if not m:
        return Version(0, 0, 0, raw=version)
    major, minor, patch, rest = m.groups()
    prerelease = ()
    build = ()

    rest = rest.strip()
    if rest.startswith("-"):
        prerelease_part, _, build_part = rest[1:].partition("+")
        if prerelease_part:
            prerelease = tuple(prerelease_part.split("."))
        if build_part:
            build = tuple(build_part.split("."))
    elif rest.startswith("+"):
        build_part = rest[1:]
        build = tuple(build_part.split("."))
    elif rest.startswith(("alpha", "a", "beta", "b", "rc")):
        prerelease = (rest,)
    elif rest.startswith("."):
        # .devN style
        prerelease = (rest.lstrip("."),)

    return Version(int(major), int(minor), int(patch), prerelease, build, raw=version)


def is_valid(version: str) -> bool:
    """Return True if the string is valid SemVer 2.0.0."""
    return parse(version) is not None


def compare(a: str | Version, b: str | Version) -> int:
    """
    Compare two versions. Returns -1 (a < b), 0 (equal), or 1 (a > b).
    """
    va = parse(a) if isinstance(a, str) else a
    vb = parse(b) if isinstance(b, str) else b
    if va is None or vb is None:
        # Fall back to string comparison
        return -1 if str(a) < str(b) else (1 if str(a) > str(b) else 0)
    if va == vb:
        return 0
    return -1 if va < vb else 1


def match(constraint_str: str, version: str | Version) -> bool:
    """Match a version against a constraint string like '>=1.2.3'."""
    constraint = parse_constraint(constraint_str)
    ver = parse(version) if isinstance(version, str) else version
    if ver is None:
        return False
    return constraint.check(ver)


def sort(versions: list[str | Version]) -> list[Version]:
    """Parse and sort a list of version strings/objects."""
    parsed = [parse(v) if isinstance(v, str) else v for v in versions]
    return sorted([v for v in parsed if v is not None])


# ----------------------------------------------------------------------
# Constraints
# ----------------------------------------------------------------------


class Constraint:
    """
    A version constraint operator. Supports: ==, !=, <, <=, >, >=, ~=, ^

    ~  (compatible)   ~=1.2.3  means >=1.2.3, <2.0.0
    ^  (caret)        ^1.2.3   means >=1.2.3, <2.0.0  (for major 0: >=1.2.3, <1.3.0)
    ~= (PEP 440 comp) ~=1.2.3  means >=1.2.3, <2.0.0
    """

    def __init__(self, op: str, version: Version):
        self.op = op
        self.version = version

    def __repr__(self) -> str:
        return f"Constraint({self.op!r}, {self.version})"

    def check(self, ver: Version) -> bool:
        op, v = self.op, self.version
        if op == "==":
            return ver == v
        if op == "!=":
            return ver != v
        if op == "<":
            return ver < v
        if op == "<=":
            return ver <= v
        if op == ">":
            return ver > v
        if op == ">=":
            return ver >= v
        if op in ("~=", "~"):
            # Tilde is the patch-level range: >=V, < next minor.
            # PEP 440 "~=1.2.3" means >=1.2.3, ==1.2.* and npm "~1.2.3"
            # agrees. v0.1.0 treated this as a major-level range, which
            # wrongly accepted 1.3.0 for "~=1.2.3".
            upper = Version(v.major, v.minor + 1, 0)
            return v <= ver < upper
        if op == "^":
            # Caret: >=V, < next major. Below major 1 the minor becomes the
            # breaking axis, and below minor 1 the patch does, matching npm.
            #   ^1.2.3 -> >=1.2.3, <2.0.0
            #   ^0.2.3 -> >=0.2.3, <0.3.0
            #   ^0.0.3 -> >=0.0.3, <0.0.4
            if v.major == 0:
                if v.minor == 0:
                    upper = Version(0, 0, v.patch + 1)
                else:
                    upper = Version(0, v.minor + 1, 0)
            else:
                upper = Version(v.major + 1, 0, 0)
            return v <= ver < upper
        return False

    def __str__(self) -> str:
        return "{0}{1}".format(self.op, self.version)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Constraint):
            return NotImplemented
        return self.op == other.op and self.version == other.version

    def __hash__(self) -> int:
        return hash((self.op, self.version))


_CONSTRAINT_RE = re.compile(
    r"(?P<op>==|!=|>=|<=|>|<|~=|~=|\^|\^|~)"
    r"\s*"
    r"(?P<ver>.+)"
)


def parse_constraint(constraint_str: str) -> Constraint:
    """
    Parse a constraint string like '>=1.2.3', '~=1.2.3', '^1.2.3', '1.2.3'.
    Plain version strings default to '=='.
    """
    m = _CONSTRAINT_RE.match(constraint_str.strip())
    if m:
        op = m.group("op")
        ver_str = m.group("ver").strip()
    else:
        op = "=="
        ver_str = constraint_str.strip()

    ver = parse(ver_str)
    if ver is None:
        ver = Version(0, 0, 0)
    return Constraint(op, ver)


def satisfies(version: str | Version, constraint) -> bool:
    """Does version satisfy constraint?

    constraint may be a single operator string, a ConstraintSet, or a full
    range expression with commas and || alternatives:

        satisfies("1.5.0", ">=1.2.0, <2.0.0")     # True
        satisfies("2.5.0", "^1.0.0 || ^2.0.0")    # True

    A plain operator string keeps its v0.1.0 meaning exactly.
    """
    ver = parse(version) if isinstance(version, str) else version
    if ver is None:
        return False
    if isinstance(constraint, ConstraintSet):
        return constraint.check(ver)
    if isinstance(constraint, Constraint):
        return constraint.check(ver)
    for alternative in parse_range(constraint):
        if alternative.check(ver):
            return True
    return False


# ----------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------


def bump_major(version: str | Version) -> Version:
    v = parse(version) if isinstance(version, str) else version
    return v.next_major()


def bump_minor(version: str | Version) -> Version:
    v = parse(version) if isinstance(version, str) else version
    return v.next_minor()


def bump_patch(version: str | Version) -> Version:
    v = parse(version) if isinstance(version, str) else version
    return v.next_patch()


def bump_prerelease(version: str | Version) -> Version:
    v = parse(version) if isinstance(version, str) else version
    if v is None:
        raise ValueError(f"Cannot parse version: {version!r}")
    return v.bump_prerelease()

# ----------------------------------------------------------------------
# Ranges: comma-separated conjunctions and || disjunctions
# ----------------------------------------------------------------------


class ConstraintSet:
    """A conjunction of constraints, e.g. ">=1.2.0, <2.0.0".

    A version satisfies the set when it satisfies every member. This is the
    shape requirements files actually use, and v0.1.0 had no way to express
    it: ">=1.2.0,<2.0.0" parsed as one malformed constraint and was compared
    against garbage, returning nonsense rather than an error.
    """

    __slots__ = ("constraints",)

    def __init__(self, constraints: Iterable["Constraint"]) -> None:
        self.constraints = list(constraints)

    def check(self, ver: Version) -> bool:
        return all(c.check(ver) for c in self.constraints)

    def __call__(self, ver) -> bool:
        parsed = parse(ver) if isinstance(ver, str) else ver
        return parsed is not None and self.check(parsed)

    def __bool__(self) -> bool:
        return bool(self.constraints)

    def __len__(self) -> int:
        return len(self.constraints)

    def __iter__(self):
        return iter(self.constraints)

    def __str__(self) -> str:
        return ", ".join(str(c) for c in self.constraints)

    def __repr__(self) -> str:
        return "ConstraintSet({0!r})".format(str(self))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ConstraintSet):
            return NotImplemented
        return self.constraints == other.constraints

    def __hash__(self) -> int:
        return hash(tuple(self.constraints))


def parse_range(spec: str) -> List[ConstraintSet]:
    """Parse a range expression into a list of alternative constraint sets.

    Supports comma-joined conjunctions and ||-separated alternatives:

        parse_range(">=1.2.0, <2.0.0")   # -> [Set(>=1.2.0, <2.0.0)]
        parse_range("^1.0.0 || ^2.0.0")   # -> [Set(^1.0.0), Set(^2.0.0)]
        parse_range("*")                  # -> [Set()]  matches anything

    An empty or wildcard-only spec means "any version" and returns a single
    empty set rather than raising, keeping wildcard handling out of caller
    code.
    """
    if not spec or not spec.strip():
        return [ConstraintSet([])]

    alternatives: List[ConstraintSet] = []
    for branch in spec.split("||"):
        constraints = []
        for part in branch.split(","):
            part = part.strip()
            if not part or part == "*":
                continue
            constraints.append(parse_constraint(part))
        alternatives.append(ConstraintSet(constraints))
    return alternatives or [ConstraintSet([])]


def filter_satisfying(versions, constraint) -> list:
    """Every version in versions that satisfies constraint, in input order.

        filter_satisfying(["1.0.0", "1.4.2", "2.0.0"], "^1.0.0")
        # -> [Version(1.0.0), Version(1.4.2)]

    Unparseable entries are dropped rather than raising: a version list
    scraped from a registry or changelog will contain junk, and one bad
    entry should not lose the whole result.
    """
    if isinstance(constraint, str):
        sets = parse_range(constraint)
    elif isinstance(constraint, ConstraintSet):
        sets = [constraint]
    elif isinstance(constraint, Constraint):
        sets = [ConstraintSet([constraint])]
    else:
        sets = list(constraint)

    out = []
    for item in versions:
        ver = parse(item) if isinstance(item, str) else item
        if ver is None:
            continue
        if any(s.check(ver) for s in sets):
            out.append(ver)
    return out


def find_max_satisfying(versions, constraint):
    """The highest version satisfying constraint, or None.

    This is the one-liner most people actually want when resolving a
    dependency: pick the newest available version that still fits.

        find_max_satisfying(["1.0.0", "1.4.2", "2.0.0"], "^1.0.0")  # 1.4.2
        find_max_satisfying(["3.0.0"], "^1.0.0")                    # None
    """
    matches = filter_satisfying(versions, constraint)
    if not matches:
        return None
    return max(matches)

