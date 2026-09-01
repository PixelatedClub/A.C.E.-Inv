from __future__ import annotations

import os
import unittest
import uuid

from inventory_app.single_instance import SingleInstanceGuard


@unittest.skipUnless(os.name == "nt", "Named-mutex behavior is Windows-specific.")
class SingleInstanceTests(unittest.TestCase):
    def test_only_one_guard_can_own_the_named_mutex(self) -> None:
        name = rf"Local\TeamShapes.ACE.Tests.{uuid.uuid4()}"
        first = SingleInstanceGuard.acquire(name)
        second = SingleInstanceGuard.acquire(name)
        try:
            self.assertTrue(first.is_primary)
            self.assertFalse(second.is_primary)
        finally:
            second.close()
            first.close()

        replacement = SingleInstanceGuard.acquire(name)
        try:
            self.assertTrue(replacement.is_primary)
        finally:
            replacement.close()


if __name__ == "__main__":
    unittest.main()
