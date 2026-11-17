"""Unit tests for deduplication and hashing logic using standard library."""
import unittest
from src.dedup import normalize_string, compute_idempotency_hash

class TestDeduplication(unittest.TestCase):
    def test_normalize_string(self):
        self.assertEqual(normalize_string("  1005 W Burnside St.  "), "1005 w burnside st")
        self.assertEqual(normalize_string("Powell's City of Books!"), "powells city of books")

    def test_compute_idempotency_hash_determinism(self):
        hash1 = compute_idempotency_hash("client_a", "1005 W Burnside St", "storefront_audit")
        hash2 = compute_idempotency_hash("CLIENT_A", "  1005 w burnside st.  ", "STOREFRONT_AUDIT")
        self.assertEqual(hash1, hash2, "Hashes must match regardless of casing or punctuation.")

    def test_different_locations_produce_different_hashes(self):
        hash1 = compute_idempotency_hash("client_a", "1005 W Burnside St", "storefront_audit")
        hash2 = compute_idempotency_hash("client_a", "1025 SE Grand Ave", "storefront_audit")
        self.assertNotEqual(hash1, hash2)

if __name__ == "__main__":
    unittest.main()
