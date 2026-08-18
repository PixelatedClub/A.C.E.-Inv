from __future__ import annotations

import unittest

from inventory_app.ui import CREDIT_QUOTES


class CreditQuoteTests(unittest.TestCase):
    def test_first_checkout_contact_quote_is_available(self) -> None:
        self.assertIn(
            {
                "text": '"if you find my first ever checkout you can contact me"',
                "author": "Ethan Williams",
            },
            CREDIT_QUOTES,
        )


if __name__ == "__main__":
    unittest.main()
