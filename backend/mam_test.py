import unittest

import mam


class MamTest(unittest.TestCase):

    def test_basicballot(self):
        self.assertEqual(
            ["a", "b", "c"], mam.MaximizeAffirmedMajorities([["a", "b", "c"]])
        )

    def test_tupleballot(self):
        self.assertEqual(
            ["a", "b", "c"],
            mam.MaximizeAffirmedMajorities(
                [
                    [
                        ("a",),
                        ("b",),
                        ("c"),
                    ]
                ]
            ),
        )

    def test_unanimity(self):
        self.assertEqual(
            ["a", "b", "c"],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["a", "b", "c"],
                ]
            ),
        )

    def test_outvoted(self):
        self.assertEqual(
            ["c", "b", "a"],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["c", "b", "a"],
                    ["c", "b", "a"],
                ]
            ),
        )

    def test_ambivalence(self):
        self.assertEqual(
            ["a", "b", "c"],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", ("b", "c")],
                    [("a", "b"), "c"],
                ]
            ),
        )

    def test_full_tie(self):
        self.assertEqual(
            [{"a", "b", "c"}, {"d", "e"}],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["b", "c", "a"],
                    ["c", "a", "b"],
                    [("d", "e")],
                    [("e", "d")],
                ],
                tiebreaker=mam.Tiebreaker.NONE,
            ),
        )

    def test_broken_tie_RVH(self):
        self.assertEqual(
            ["a", "b", "c", {"d", "e"}],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["b", "c", "a"],
                    ["c", "a", "b"],
                    [("d", "e")],
                    [("e", "d")],
                ],
                tiebreaker=mam.Tiebreaker.RVH,
                seed=1,
            ),
        )
        self.assertEqual(
            ["c", "a", "b", {"d", "e"}],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["b", "c", "a"],
                    ["c", "a", "b"],
                    [("d", "e")],
                    [("e", "d")],
                ],
                tiebreaker=mam.Tiebreaker.RVH,
                seed=5,
            ),
        )

    def test_broken_tie_LINEAR(self):
        self.assertEqual(
            ["a", "b", "c", "d", "e"],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["b", "c", "a"],
                    ["c", "a", "b"],
                    [("d", "e")],
                    [("e", "d")],
                ],
                tiebreaker=mam.Tiebreaker.LINEAR,
                seed=1,
            ),
        )
        self.assertEqual(
            ["c", "a", "b", "d", "e"],
            mam.MaximizeAffirmedMajorities(
                [
                    ["a", "b", "c"],
                    ["b", "c", "a"],
                    ["c", "a", "b"],
                    [("d", "e")],
                    [("e", "d")],
                ],
                tiebreaker=mam.Tiebreaker.LINEAR,
                seed=5,
            ),
        )

    def test_known_outcome(self):
        self.assertEqual(
            ["b", "c", "a"],
            mam.MaximizeAffirmedMajorities(
                [["a", "b", "c"]] * 36
                + [["b", "a", "c"]] * 12
                + [["b", "c", "a"]] * 8
                + [["c", "b", "a"]] * 44
            ),
        )

    def test_rps(self):
        self.assertEqual(
            ["r", "s", "p"],
            mam.MaximizeAffirmedMajorities(
                [["r", "s", "p"]] * 40 + [["s", "p", "r"]] * 35 + [["p", "r", "s"]] * 25
            ),
        )

    def test_wikipedia_tennesee(self):
        self.assertEqual(
            ["nashville", "chattanooga", "knoxville", "memphis"],
            mam.MaximizeAffirmedMajorities(
                [["memphis", "nashville", "chattanooga", "knoxville"]] * 42
                + [["nashville", "chattanooga", "knoxville", "memphis"]] * 26
                + [["chattanooga", "knoxville", "nashville", "memphis"]] * 15
                + [["knoxville", "chattanooga", "nashville", "memphis"]] * 17
            ),
        )


if __name__ == "__main__":
    unittest.main()
