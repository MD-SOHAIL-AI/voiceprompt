import unittest

from voiceprompt.replacements import apply_replacements


class ReplacementTests(unittest.TestCase):
    def test_handles_programming_terms_with_punctuation(self) -> None:
        text = apply_replacements("use c plus plus and C++", {"c plus plus": "C++", "C++": "C++"})
        self.assertEqual(text, "use C++ and C++")

    def test_does_not_replace_inside_longer_word(self) -> None:
        self.assertEqual(apply_replacements("cloudy cloud", {"cloud": "Claude"}), "cloudy Claude")


if __name__ == "__main__":
    unittest.main()
