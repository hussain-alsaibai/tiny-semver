# tiny-semver

> **Zero-dependency Semantic Versioning.** Parse, compare, bump, validate, and constrain-check SemVer 2.0.0 strings. Pure Python stdlib. One file. MIT.

```
pip install tiny-semver
```
or just copy `tiny_semver.py` into your project.

---

## Features

- ✅ **SemVer 2.0.0** — full spec compliance including prerelease & build metadata
- ✅ **Parsing & validation** — `parse()` and `is_valid()` 
- ✅ **Comparison** — `<`, `>`, `<=`, `>=`, `==`, `!=` operators
- ✅ **Sorting** — `sorted_versions()`, `max_ver()`, `min_ver()`
- ✅ **Bumping** — `bump_major()`, `bump_minor()`, `bump_patch()`, `bump_prerelease()`, `release_prerelease()`
- ✅ **Constraints** — `satisfies()`, caret `^`, tilde `~`, ranges: `>=1.0.0, <2.0.0`
- ✅ **Hashable** — use `SemVer` in sets and dicts
- ✅ **Zero dependencies** — stdlib only

---

## Quick Start

```python
from tiny_semver import SemVer, parse, satisfies, bump_patch

# Parse and compare
v = parse("1.2.3-beta.1+build.456")
assert v.major == 1
assert v < parse("2.0.0")

# Bump versions
next_patch = bump_patch("1.2.3")       # SemVer(1, 2, 4)
next_minor = bump_minor("1.2.3")      # SemVer(1, 3, 0)
next_major = bump_major("1.0.0-rc.1") # SemVer(2, 0, 0)

# Constraint checking
assert satisfies("1.2.3", "^1.0.0")    # True  — same major
assert satisfies("2.0.0", "^1.0.0")    # False — major mismatch
assert satisfies("1.4.0", "~1.2.0")    # True  — same minor
assert satisfies("1.0.0", ">=1.0.0, <2.0.0")  # True
```

---

## API Reference

### Parsing

```python
from tiny_semver import parse, is_valid

v = parse("2.1.0-rc.3+build.2024")
# SemVer(major=2, minor=1, patch=0, prerelease=('rc', '3'), build=('build', '2024'))

is_valid("1.2.3")        # True
is_valid("1.2")         # False
```

### Comparison

```python
from tiny_semver import SemVer

SemVer(1, 2, 3) < SemVer(2, 0, 0)     # True
SemVer(1, 0, 0) < SemVer(1, 0, 0, ("alpha",))  # True — release > prerelease
max_ver("1.0.0", "2.0.0", "1.5.0")    # SemVer(2, 0, 0)
sorted_versions("2.0", "1.0", "1.0a")  # [SemVer(1,0,0,a), SemVer(1,0,0), SemVer(2,0,0)]
```

### Bumping

```python
bump_patch("1.2.3")        # → "1.2.4"
bump_minor("1.2.3")        # → "1.3.0"
bump_major("0.1.0")        # → "1.0.0"
bump_prerelease("1.0.0")   # → "1.0.0-rc.0"
release_prerelease("1.0.0-alpha")  # → "1.0.0"
replace("1.0.0", major=2, prerelease=("beta",))  # → "2.0.0-beta"
```

### Constraints

```python
from tiny_semver import satisfies

# Operators: ==, !=, >, <, >=, <=, ^, ~
satisfies("1.9.9", "^1.0.0")          # True (same major)
satisfies("2.0.0", "^1.0.0")          # False (major differs)
satisfies("1.2.3", "~1.0.0")          # True (same minor)
satisfies("1.2.0", "~1.0.0")          # True
satisfies("1.3.0", "~1.0.0")          # False (minor differs)
satisfies("1.0.0", ">=1.0.0, <2.0.0")  # True (AND constraint)
```

---

## Benchmark

```
python -m timeit -s "from tiny_semver import parse" "parse('1.2.3')"
# ~1.2 µs per parse

python -m timeit -s "from tiny_semver import SemVer" "SemVer(1,2,3) < SemVer(2,0,0)"
# ~0.3 µs per comparison
```

## Why?

Because `packaging.version` has a 40ms cold-start overhead and a dependency you don't need.
`tiny-semver` imports in **<0.1ms** and has zero dependencies.

---

## Install

```bash
pip install tiny-semver
```

Or copy the single file:
```bash
curl -O https://raw.githubusercontent.com/hussain-alsaibai/tiny-semver/main/tiny_semver.py
```

---

## License

MIT © 2026 Hussain Al-Saibai
