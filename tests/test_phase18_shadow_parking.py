import unittest
from scripts.contractkv_shadow_parking import ShadowParking

class Request:
    request_id = "r"
    num_computed_tokens = 128

class ShadowParkingTests(unittest.TestCase):
    def test_park_wake_preserves_progress(self):
        parking = ShadowParking(); request = Request()
        self.assertTrue(parking.park(request, 20, "foreground"))
        self.assertEqual(parking.wake(19), [])
        item = parking.wake(20)[0]
        self.assertIs(item.request, request)
        self.assertEqual(item.computed_tokens, 128)

    def test_cancel_prevents_wake(self):
        parking = ShadowParking(); parking.park(Request(), 20, "foreground")
        self.assertIsNotNone(parking.cancel("r"))
        self.assertEqual(parking.wake(20), [])
