import unittest
from procurement import recommend


class ReplenishmentTests(unittest.TestCase):
    def calculate(self, **changes):
        args = dict(sku="TEST", supplier="SUPPLIER", daily_sales=[10]*28,
                    on_hand=30, in_transit=20, lead_days=7)
        args.update(changes)
        return recommend(**args)

    def test_basic_coverage(self):
        self.assertEqual(self.calculate().quantity, 90)

    def test_inbound_changes_order(self):
        self.assertEqual(self.calculate(in_transit=50).quantity, 60)

    def test_isolated_spike_does_not_inflate_regular_order(self):
        result = self.calculate(daily_sales=[10]*27+[1000])
        self.assertEqual(result.quantity, 90)
        self.assertEqual(result.excluded_spikes, 1)

    def test_growth_and_pack_size(self):
        self.assertEqual(self.calculate(growth=0.2, pack_size=10).quantity, 120)

    def test_no_negative_order(self):
        self.assertEqual(self.calculate(on_hand=1000).quantity, 0)

    def test_invalid_input(self):
        for value in [-1, float("nan"), float("inf")]:
            with self.assertRaises(ValueError):
                self.calculate(on_hand=value)

    def test_recommendation_needs_human_review(self):
        self.assertEqual(self.calculate().status, "draft_requires_review")


if __name__ == "__main__":
    unittest.main()
