import unittest

from app.system.profiler import AutoTuner, HardwareSnapshot


class AutoTunerTest(unittest.TestCase):
    def test_low_profile_bounds_memory_and_translation_churn(self):
        snapshot = HardwareSnapshot(
            os_label="Windows",
            python_label="3.11",
            cpu_cores=2,
            total_ram_gb=8,
            free_disk_gb=20,
            gpu_name="",
            storage_path="C:\\",
        )

        profile = AutoTuner().tune(snapshot)

        self.assertEqual(profile.name, "low")
        self.assertEqual(profile.audio_queue_size, 1300)
        self.assertEqual(profile.max_cached_models, 1)
        self.assertGreaterEqual(profile.partial_translation_delay_ms, 600)

    def test_mid_profile_uses_cpu_backlog_sized_audio_queue(self):
        snapshot = HardwareSnapshot(
            os_label="Windows",
            python_label="3.11",
            cpu_cores=6,
            total_ram_gb=16,
            free_disk_gb=60,
            gpu_name="",
            storage_path="C:\\",
        )

        profile = AutoTuner().tune(snapshot)

        self.assertEqual(profile.name, "mid")
        self.assertEqual(profile.audio_queue_size, 2000)

    def test_high_profile_allows_secondary_model_cache(self):
        snapshot = HardwareSnapshot(
            os_label="Windows",
            python_label="3.11",
            cpu_cores=12,
            total_ram_gb=32,
            free_disk_gb=100,
            gpu_name="NVIDIA",
            storage_path="C:\\",
        )

        profile = AutoTuner().tune(snapshot)

        self.assertEqual(profile.name, "high")
        self.assertEqual(profile.audio_queue_size, 4000)
        self.assertTrue(profile.preload_secondary_model)
        self.assertEqual(profile.max_cached_models, 2)


if __name__ == "__main__":
    unittest.main()
