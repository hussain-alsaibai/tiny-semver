import unittest
from tiny_semver import (
    SemVer, parse, is_valid, bump_major, bump_minor, bump_patch,
    bump_prerelease, release_prerelease, replace, satisfies, Comp,
    max_ver, min_ver, sorted_versions,
)


class TestSemVerParsing(unittest.TestCase):
    def test_basic(self):
        v = parse("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertEqual(v.prerelease, ())
        self.assertEqual(v.build, ())

    def test_prerelease(self):
        v = parse("1.0.0-alpha.1")
        self.assertEqual(v.prerelease, ("alpha", "1"))

    def test_build(self):
        v = parse("1.0.0+build.2024")
        self.assertEqual(v.build, ("build", "2024"))

    def test_prerelease_and_build(self):
        v = parse("1.0.0-beta.2+build.123")
        self.assertEqual(v.prerelease, ("beta", "2"))
        self.assertEqual(v.build, ("build", "123"))

    def test_invalid_wrong_format(self):
        with self.assertRaises(ValueError):
            parse("1.2")
        with self.assertRaises(ValueError):
            parse("v1.2.3")
        with self.assertRaises(ValueError):
            parse("1.02.3")

    def test_is_valid(self):
        self.assertTrue(is_valid("1.2.3"))
        self.assertTrue(is_valid("0.0.1-alpha"))
        self.assertFalse(is_valid("1.2"))
        self.assertFalse(is_valid("not-a-version"))


class TestSemVerComparison(unittest.TestCase):
    def test_equality(self):
        self.assertEqual(parse("1.2.3"), parse("1.2.3"))
        # Build metadata excluded from equality
        self.assertEqual(parse("1.2.3+build"), parse("1.2.3"))

    def test_less_than(self):
        self.assertLess(parse("1.2.3"), parse("2.0.0"))
        self.assertLess(parse("1.2.3"), parse("1.3.0"))
        self.assertLess(parse("1.2.3"), parse("1.2.4"))
        # Prerelease < release
        self.assertLess(parse("1.0.0-alpha"), parse("1.0.0"))
        self.assertLess(parse("1.0.0-alpha.1"), parse("1.0.0-alpha.2"))
        self.assertLess(parse("1.0.0-alpha"), parse("1.0.0-beta"))

    def test_sorting(self):
        versions = ["2.0.0", "1.0.0", "1.0.0-alpha", "1.0.0-beta", "1.0.1"]
        sorted_v = sorted_versions(*versions)
        self.assertEqual([str(v) for v in sorted_v],
                         ["1.0.0-alpha", "1.0.0-beta", "1.0.0", "1.0.1", "2.0.0"])

    def test_max_min(self):
        self.assertEqual(max_ver("1.0.0", "2.0.0", "1.5.0"), parse("2.0.0"))
        self.assertEqual(min_ver("1.0.0", "2.0.0", "1.5.0"), parse("1.0.0"))


class TestSemVerBumping(unittest.TestCase):
    def test_bump_major(self):
        self.assertEqual(bump_major("1.2.3"), parse("2.0.0"))
        self.assertEqual(bump_major("0.1.0"), parse("1.0.0"))

    def test_bump_minor(self):
        self.assertEqual(bump_minor("1.2.3"), parse("1.3.0"))

    def test_bump_patch(self):
        self.assertEqual(bump_patch("1.2.3"), parse("1.2.4"))

    def test_bump_prerelease(self):
        v = bump_prerelease("1.2.3")
        self.assertEqual(v, SemVer(1, 2, 3, ("rc", "0")))

    def test_release_prerelease(self):
        v = release_prerelease("1.2.3-alpha")
        self.assertEqual(v, parse("1.2.3"))

    def test_replace(self):
        v = replace("1.2.3", minor=5, prerelease=("beta",))
        self.assertEqual(v, SemVer(1, 5, 3, ("beta",)))


class TestConstraints(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(satisfies("1.2.3", "==1.2.3"))
        self.assertFalse(satisfies("1.2.3", "==1.2.4"))

    def test_gte(self):
        self.assertTrue(satisfies("1.2.3", ">=1.0.0"))
        self.assertFalse(satisfies("0.9.0", ">=1.0.0"))

    def test_caret(self):
        self.assertTrue(satisfies("1.2.3", "^1.0.0"))
        self.assertTrue(satisfies("1.9.9", "^1.0.0"))
        self.assertFalse(satisfies("2.0.0", "^1.0.0"))
        self.assertFalse(satisfies("0.2.3", "^1.0.0"))

    def test_tilde(self):
        self.assertTrue(satisfies("1.2.3", "~1.2.0"))
        self.assertFalse(satisfies("1.3.0", "~1.2.0"))

    def test_complex_constraint(self):
        self.assertTrue(satisfies("1.2.3", ">=1.0.0, <2.0.0"))
        self.assertFalse(satisfies("2.0.0", ">=1.0.0, <2.0.0"))


class TestStringRepr(unittest.TestCase):
    def test_str(self):
        self.assertEqual(str(parse("1.2.3")), "1.2.3")
        self.assertEqual(str(parse("1.0.0-alpha+build")), "1.0.0-alpha+build")

    def test_repr(self):
        self.assertIn("SemVer", repr(parse("1.2.3")))

    def test_hashable(self):
        s = {parse("1.0.0"), parse("2.0.0"), parse("1.0.0")}
        self.assertEqual(len(s), 2)


if __name__ == "__main__":
    unittest.main()
