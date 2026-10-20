import unittest

from loader import protocol as p


def event(state="active", target="person", rule="1", kind="vmd"):
    return p.CameraEvent(kind, state, "1", frozenset({target}) if target else frozenset(), rule)


class DebounceTests(unittest.TestCase):
    def setUp(self):
        self.alarms = p.AlarmState(channel=1, hold=10, debounce=5)

    def test_high_until_x_seconds_after_end_not_after_start(self):
        self.alarms.apply(event(), 0)
        self.alarms.apply(event("inactive"), 8)
        self.alarms.expire(12.999)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(13)
        self.assertFalse(self.alarms.is_on("person"))

    def test_retrigger_cancels_previous_off_deadline(self):
        self.alarms.apply(event(), 0)
        self.alarms.apply(event("inactive"), 2)
        self.alarms.apply(event(), 6)
        self.alarms.expire(7)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.apply(event("inactive"), 9)
        self.alarms.expire(13)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(14)
        self.assertFalse(self.alarms.is_on("person"))

    def test_duplicate_inactive_does_not_extend_timer(self):
        self.alarms.apply(event(), 0)
        self.alarms.apply(event("inactive"), 2)
        self.alarms.apply(event("inactive"), 6)
        self.alarms.expire(7)
        self.assertFalse(self.alarms.is_on("person"))

    def test_inactive_without_active_does_not_activate(self):
        self.alarms.apply(event("inactive"), 2)
        self.assertFalse(self.alarms.is_on("person"))

    def test_independent_rules_wait_for_last_end(self):
        self.alarms.apply(event(rule="1"), 0)
        self.alarms.apply(event(rule="2"), 1)
        self.alarms.apply(event("inactive", rule="1"), 2)
        self.alarms.apply(event("inactive", rule="2"), 6)
        self.alarms.expire(7)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(11)
        self.assertFalse(self.alarms.is_on("person"))

    def test_target_specific_end_keeps_vehicle_motion(self):
        self.alarms.apply(event(), 0)
        self.alarms.apply(event(target="vehicle"), 1)
        self.alarms.apply(event("inactive"), 2)
        self.alarms.expire(7)
        self.assertFalse(self.alarms.is_on("person"))
        self.assertTrue(self.alarms.is_on("vehicle"))
        self.assertTrue(self.alarms.is_on("motion"))
        self.alarms.apply(event("inactive", target="vehicle"), 8)
        self.alarms.expire(13)
        self.assertFalse(self.alarms.is_on("motion"))

    def test_missing_end_watchdog_is_followed_by_debounce(self):
        self.alarms.apply(event(), 0)
        self.alarms.expire(10)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(15)
        self.assertFalse(self.alarms.is_on("person"))

    def test_late_tick_uses_actual_deadline(self):
        self.alarms.apply(event(), 0)
        self.alarms.expire(100)
        self.assertFalse(self.alarms.is_on("person"))

    def test_disabled_watchdog_waits_for_explicit_end(self):
        self.alarms.hold = 0
        self.alarms.apply(event(), 0)
        self.alarms.expire(1000)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.apply(event("inactive"), 1001)
        self.alarms.expire(1005)
        self.assertTrue(self.alarms.is_on("person"))
        self.alarms.expire(1006)
        self.assertFalse(self.alarms.is_on("person"))

    def test_fault_end_uses_debounce_without_watchdog(self):
        self.alarms.apply(event(kind="diskerror", target=""), 0)
        self.alarms.expire(100)
        self.assertTrue(self.alarms.is_on("disk_error"))
        self.alarms.apply(event("inactive", kind="diskerror", target=""), 101)
        self.alarms.expire(105)
        self.assertTrue(self.alarms.is_on("disk_error"))
        self.alarms.expire(106)
        self.assertFalse(self.alarms.is_on("disk_error"))

    def test_disconnect_discards_pending_off(self):
        self.alarms.apply(event(), 0)
        self.alarms.apply(event("inactive"), 2)
        self.alarms.clear()
        self.assertFalse(self.alarms.is_on("person"))
        self.assertEqual(self.alarms.pending_off, {})
