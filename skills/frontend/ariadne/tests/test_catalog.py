from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from ariadne_state.catalog import build_api_key, normalize_path, path_shape, stable_signature_hash  # noqa: E402
from ariadne_state.matcher import path_matches_any, path_matches_pattern, under_any_root  # noqa: E402


class CatalogHelpersTest(unittest.TestCase):
    def test_path_normalization_handles_framework_placeholders(self) -> None:
        self.assertEqual(normalize_path("api/orders/:orderId"), "/api/orders/{orderId}")
        self.assertEqual(normalize_path("/api/orders/<order_id>"), "/api/orders/{order_id}")
        self.assertEqual(normalize_path("/api/orders/{id}/"), "/api/orders/{id}")
        self.assertEqual(normalize_path("/api/v1/orders", rules=[{"match": r"^/api/v[0-9]+", "replace": ""}]), "/orders")
        self.assertEqual(path_shape("/orders/{id}"), "/orders/{}")
        self.assertEqual(build_api_key("get", "/orders"), "GET /orders")
        self.assertEqual(stable_signature_hash({"a": 1, "b": 2}), stable_signature_hash({"b": 2, "a": 1}))

    def test_glob_and_root_matching_cover_nested_paths(self) -> None:
        self.assertTrue(path_matches_any("src/api/nested/orders.ts", ["src/**/*.ts"]))
        self.assertTrue(path_matches_pattern("src/api/nested/orders.ts", "./src/**/*.ts"))
        self.assertTrue(under_any_root("src/api/orders.ts", ["src"]))
        self.assertFalse(under_any_root("backend/orders.ts", ["src"]))


if __name__ == "__main__":
    unittest.main()
