"""
tiny-semver — Zero-dependency Semantic Versioning (SemVer 2.0.0)

Parse, compare, bump, and validate Semantic Version strings.
Pure Python stdlib. MIT License.

Spec: https://semver.org/
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

# ----------------------------------------------------------------------
# Core types
# ----------------------------------------------------------------------

REGEX = re.compile(
    r"^(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<build>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@dataclass
class SemVer:
    """Immutable Semantic Version representation."""
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        v = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            v += "-" + ".".join(self.prerelease)
        if self.build:
            v += "+" + ".".join(self.build)
        return v

    def __repr__(self) -> str:
        return f"SemVer({self})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
            # Build metadata excluded from equality per semver spec
        )

    def __lt__(self, other: SemVer) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        self_tuple = (self.major, self.minor, self.patch)
        other_tuple = (other.major, other.minor, other.patch)
        if self_tuple != other_tuple:
            return self_tuple < other_tuple
        # Precedence: no prerelease > prerelease
        if not self.prerelease and other.prerelease:
            return False
        if self.prerelease and not other.prerelease:
            return True
        if self.prerelease and other.prerelease:
            return self._precedence_cmp(self.prerelease, other.prerelease) < 0
        return False

    def __le__(self, other: SemVer) -> bool:
        return self == other or self < other

    def __gt__(self, other: SemVer) -> bool:
        return other < self

    def __ge__(self, other: SemVer) -> bool:
        return self == other or self > other

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch, self.prerelease))

    @staticmethod
    def _precedence_cmp(a: tuple[str, ...], b: tuple[str, ...]) -> int:
        """Compare prerelease identifiers per semver spec."""
        la, lb = len(a), len(b)
        for i in range(min(la, lb)):
            av, bv = a[i], b[i]
            an = _is_numeric(av)
            bn = _is_numeric(bv)
            if an and bn:
                diff = int(av) - int(bv)
                if diff:
                    return diff
            elif an:
                return -1
            elif bn:
                return 1
            elif av < bv:
                return -1
            elif av > bv:
                return 1
        return la - lb


def _is_numeric(s: str) -> bool:
    try:
        int(s)
        return True
    except ValueError:
        return False


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------

def parse(version: str) -> SemVer:
    """Parse a semver string into a SemVer object. Raises ValueError on invalid."""
    version = version.strip()
    m = REGEX.match(version)
    if not m:
        raise ValueError(f"Invalid semantic version: {version!r}")
    gd = m.groupdict()
    major = int(gd["major"])
    minor = int(gd["minor"])
    patch = int(gd["patch"])
    prerelease = tuple(gd["prerelease"].split(".")) if gd["prerelease"] else ()
    build = tuple(gd["build"].split(".")) if gd["build"] else ()
    return SemVer(major, minor, patch, prerelease, build)


def is_valid(version: str) -> bool:
    """Return True if the string is a valid semver."""
    return REGEX.match(version.strip()) is not None


def parse_constraint(constraint: str) -> Iterator[Comp]:
    """Parse one or more constraint strings (yielding Comp objects)."""
    for part in constraint.replace(",", " ").split():
        part = part.strip()
        if not part:
            continue
        yield Comp(part)


# ----------------------------------------------------------------------
# Comparison operators
# ----------------------------------------------------------------------

class Comp:
    """Represents a single constraint: e.g. '>=1.2.3', '^2.0.0', '~3.1.0'."""

    def __init__(self, expr: str) -> None:
        self.expr = expr
        self.op, raw = self._parse(expr)
        self.base = parse(raw)

    def _parse(self, expr: str) -> tuple[str, str]:
        for op in (">=", "<=", "==", "!=", ">", "<", "^", "~"):
            if expr.startswith(op):
                return op, expr[len(op):]
        raise ValueError(f"Unknown operator in constraint: {expr!r}")

    def satisfied_by(self, version: SemVer | str) -> bool:
        if isinstance(version, str):
            version = parse(version)
        if self.op == "==":
            return version == self.base
        if self.op == "!=":
            return version != self.base
        if self.op == ">":
            return version > self.base
        if self.op == ">=":
            return version >= self.base
        if self.op == "<":
            return version < self.base
        if self.op == "<=":
            return version <= self.base
        if self.op == "^":
            # Caret: compatible with same major version
            return (
                version.major == self.base.major
                and version >= self.base
            )
        if self.op == "~":
            # Tilde: compatible with same minor version
            return (
                version.major == self.base.major
                and version.minor == self.base.minor
                and version >= self.base
            )
        return False

    def __repr__(self) -> str:
        return f"Comp({self.expr!r})"


def satisfies(version: str, constraint: str) -> bool:
    """Return True if version satisfies constraint (comma-separated or space-separated)."""
    v = parse(version)
    return all(c.satisfied_by(v) for c in parse_constraint(constraint))


# ----------------------------------------------------------------------
# Bumping
# ----------------------------------------------------------------------

def bump_major(v: SemVer | str) -> SemVer:
    """Bump major version, reset minor and patch."""
    if isinstance(v, str):
        v = parse(v)
    return SemVer(v.major + 1, 0, 0)


def bump_minor(v: SemVer | str) -> SemVer:
    """Bump minor version, reset patch."""
    if isinstance(v, str):
        v = parse(v)
    return SemVer(v.major, v.minor + 1, 0)


def bump_patch(v: SemVer | str) -> SemVer:
    """Bump patch version."""
    if isinstance(v, str):
        v = parse(v)
    return SemVer(v.major, v.minor, v.patch + 1)


def bump_prerelease(v: SemVer | str, label: str = "rc") -> SemVer:
    """Add or increment a prerelease label. '1.0.0' -> '1.0.1-rc.0'."""
    if isinstance(v, str):
        v = parse(v)
    new_pre = (f"{label}", "0")
    return SemVer(v.major, v.minor, v.patch, new_pre)


def release_prerelease(v: SemVer | str) -> SemVer:
    """Remove prerelease label (promote to stable). '1.0.0-alpha' -> '1.0.0'."""
    if isinstance(v, str):
        v = parse(v)
    return SemVer(v.major, v.minor, v.patch)


def replace(v: SemVer | str, **fields) -> SemVer:
    """Replace specific version fields and return new SemVer."""
    if isinstance(v, str):
        v = parse(v)
    return SemVer(
        major=fields.get("major", v.major),
        minor=fields.get("minor", v.minor),
        patch=fields.get("patch", v.patch),
        prerelease=fields.get("prerelease", v.prerelease),
        build=fields.get("build", v.build),
    )


# ----------------------------------------------------------------------
# Convenience
# ----------------------------------------------------------------------

def max_ver(*versions: str | SemVer) -> SemVer:
    """Return the highest SemVer from the arguments."""
    if not versions:
        raise ValueError("max_ver requires at least one version")
    parsed = [v if isinstance(v, SemVer) else parse(v) for v in versions]
    return max(parsed)


def min_ver(*versions: str | SemVer) -> SemVer:
    """Return the lowest SemVer from the arguments."""
    if not versions:
        raise ValueError("min_ver requires at least one version")
    parsed = [v if isinstance(v, SemVer) else parse(v) for v in versions]
    return min(parsed)


def sorted_versions(*versions: str | SemVer) -> list[SemVer]:
    """Return versions sorted from lowest to highest."""
    parsed = [v if isinstance(v, SemVer) else parse(v) for v in versions]
    return sorted(parsed)
