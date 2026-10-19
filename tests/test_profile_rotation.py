import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resources"))

import nova_profile_rotation as rotation  # noqa: E402


class RotationPolicyTests(unittest.TestCase):
    def make_policy(self):
        policy = rotation.RotationPolicy()
        policy.reset(0.0, "current")
        return policy

    def feed_healthy(self, policy, start=100.0, value=50.0):
        for offset in range(0, 90, 30):
            policy.observe(start + offset, value, True)

    def test_baseline_needs_three_samples(self):
        policy = self.make_policy()
        self.assertFalse(policy.observe(100.0, 50.0, True))
        self.assertFalse(policy.observe(130.0, 50.0, True))
        self.assertFalse(policy.observe(160.0, 50.0, True))

    def test_three_degraded_samples_trigger(self):
        policy = self.make_policy()
        self.feed_healthy(policy)
        self.assertFalse(policy.observe(190.0, 120.0, True))
        self.assertFalse(policy.observe(220.0, 120.0, True))
        self.assertTrue(policy.observe(250.0, 120.0, True))

    def test_single_spike_does_not_trigger(self):
        policy = self.make_policy()
        self.feed_healthy(policy)
        self.assertFalse(policy.observe(190.0, 120.0, True))
        self.assertFalse(policy.observe(220.0, 50.0, True))
        self.assertFalse(policy.observe(250.0, 50.0, True))

    def test_canary_failures_trigger(self):
        policy = self.make_policy()
        self.feed_healthy(policy)
        policy.observe(190.0, None, False)
        policy.observe(220.0, None, False)
        self.assertTrue(policy.observe(250.0, None, False))

    def test_active_time_blocks_early_rotation(self):
        policy = self.make_policy()
        policy.observe(10.0, 50.0, True)
        policy.observe(40.0, 120.0, True)
        self.assertFalse(policy.observe(70.0, 120.0, True))
        self.assertFalse(policy.can_rotate(70.0, "group", "AWG Proton"))

    def test_explicit_profile_never_rotates(self):
        policy = self.make_policy()
        self.feed_healthy(policy)
        policy.observe(190.0, 120.0, True)
        policy.observe(220.0, 120.0, True)
        policy.observe(250.0, 120.0, True)
        candidate = rotation.ProfileCandidate("fast", "AWG Proton", 40.0, 200.0, 0.0, 0)
        decision = policy.decide(
            250.0, mode="profile", current_id="current", current_group="AWG Proton",
            current_direct_ms=100.0, candidates=[candidate],
        )
        self.assertFalse(decision.rotate)

    def test_auto_only_rotates_proton(self):
        policy = self.make_policy()
        candidate = rotation.ProfileCandidate("fast", "VLESS", 40.0, 200.0, 0.0, 0)
        self.assertFalse(policy.can_rotate(200.0, "auto", "VLESS"))
        self.assertTrue(policy.can_rotate(200.0, "auto", "AWG Proton"))

    def test_cooldown_blocks_repeat(self):
        policy = self.make_policy()
        policy.note_rotation(300.0, True)
        self.assertFalse(policy.can_rotate(301.0, "group", "AWG Proton"))
        self.assertFalse(policy.can_rotate(1199.0, "group", "AWG Proton"))
        self.assertTrue(policy.can_rotate(1201.0, "group", "AWG Proton"))

    def test_max_two_rotations_per_hour(self):
        policy = self.make_policy()
        policy.note_rotation(1000.0, True)
        policy.note_rotation(1100.0, True)
        self.assertFalse(policy.can_rotate(2001.0, "group", "AWG Proton"))
        self.assertTrue(policy.can_rotate(4702.0, "group", "AWG Proton"))

    def test_reset_relearns_baseline(self):
        policy = self.make_policy()
        self.feed_healthy(policy)
        self.assertIsNotNone(policy.baseline_ms)
        policy.reset(500.0, "other")
        self.assertIsNone(policy.baseline_ms)
        self.assertFalse(policy.observe(600.0, 400.0, True))

    def test_hold_log_is_rate_limited(self):
        policy = self.make_policy()
        self.assertTrue(policy.should_log_hold(100.0))
        self.assertFalse(policy.should_log_hold(200.0))
        self.assertTrue(policy.should_log_hold(700.0))


class CandidateTests(unittest.TestCase):
    def test_candidate_must_be_thirty_percent_better(self):
        current = rotation.ProfileCandidate("current", "AWG Proton", 100.0, 1.0, 0.0, 0)
        fast = rotation.ProfileCandidate("fast", "AWG Proton", 69.0, 2.0, 0.0, 0)
        slow = rotation.ProfileCandidate("slow", "AWG Proton", 71.0, 3.0, 0.0, 0)
        self.assertEqual(
            rotation.choose_candidate("current", "AWG Proton", 100.0, [current, fast]).profile_id,
            "fast",
        )
        self.assertIsNone(rotation.choose_candidate("current", "AWG Proton", 100.0, [current, slow]))

    def test_failing_channel_accepts_smaller_gain(self):
        candidate = rotation.ProfileCandidate("fast", "AWG Proton", 85.0, 2.0, 0.0, 0)
        self.assertIsNotNone(
            rotation.choose_candidate("current", "AWG Proton", 100.0, [candidate], failing=True)
        )
        candidate = rotation.ProfileCandidate("fast", "AWG Proton", 86.0, 2.0, 0.0, 0)
        self.assertIsNone(
            rotation.choose_candidate("current", "AWG Proton", 100.0, [candidate], failing=True)
        )

    def test_failed_candidate_is_excluded(self):
        failed = rotation.ProfileCandidate("failed", "AWG Proton", 20.0, 1.0, 2.0, 1)
        failed_later = rotation.ProfileCandidate("later", "AWG Proton", 20.0, 1.0, 2.0, 0)
        self.assertIsNone(
            rotation.choose_candidate("current", "AWG Proton", 100.0, [failed, failed_later])
        )

    def test_other_group_is_excluded(self):
        candidate = rotation.ProfileCandidate("other", "VLESS", 20.0, 1.0, 0.0, 0)
        self.assertIsNone(rotation.choose_candidate("current", "AWG Proton", 100.0, [candidate]))

    def test_no_current_rtt_returns_fastest(self):
        one = rotation.ProfileCandidate("one", "AWG Proton", 80.0, 1.0, 0.0, 0)
        two = rotation.ProfileCandidate("two", "AWG Proton", 40.0, 1.0, 0.0, 0)
        self.assertEqual(
            rotation.choose_candidate("current", "AWG Proton", None, [one, two]).profile_id,
            "two",
        )


if __name__ == "__main__":
    unittest.main()
