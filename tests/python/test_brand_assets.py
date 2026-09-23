import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class BrandAssetsTest(unittest.TestCase):
    def test_brand_assets_are_safe_responsive_svg(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "validate_brand_assets.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("lighthouse-mark.svg", result.stdout)
        self.assertIn("icon.svg", result.stdout)


if __name__ == "__main__":
    unittest.main()
