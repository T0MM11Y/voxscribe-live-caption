import unittest

from app.ui.subtitle_overlay import SubtitleOverlay


class FakeConfig:
    def __init__(self):
        self.values = {
            "overlay_font_size": 16,
            "overlay_font_profile": "subtitle_v3",
            "overlay_compact": False,
            "overlay_x": None,
            "overlay_y": None,
        }

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class FakeRoot:
    def __init__(self, width=1366, height=768):
        self.width = width
        self.height = height

    def winfo_screenwidth(self):
        return self.width

    def winfo_screenheight(self):
        return self.height


class FakeWindow:
    def winfo_exists(self):
        return True


class FakeShowWindow(FakeWindow):
    def __init__(self):
        self.deiconified = 0
        self.lifted = 0
        self.attributes_calls = []

    def deiconify(self):
        self.deiconified += 1

    def lift(self):
        self.lifted += 1

    def attributes(self, *args):
        self.attributes_calls.append(args)


class FakeGeometryWindow(FakeWindow):
    def __init__(self):
        self.geometry_calls = []
        self.update_calls = 0

    def geometry(self, value):
        self.geometry_calls.append(value)

    def update_idletasks(self):
        self.update_calls += 1


class SchedulingRoot(FakeRoot):
    def __init__(self, width=1366, height=768):
        super().__init__(width, height)
        self.after_calls = []
        self.cancelled_jobs = []

    def after(self, delay_ms, callback):
        job = f"job-{len(self.after_calls) + 1}"
        self.after_calls.append((job, delay_ms, callback))
        return job

    def after_cancel(self, job):
        self.cancelled_jobs.append(job)


def make_overlay(width=1366, height=768):
    return SubtitleOverlay(FakeRoot(width, height), FakeConfig(), lambda: None, {})


class SubtitleOverlayLayoutTest(unittest.TestCase):
    def test_overlay_target_size_is_fixed_single_view(self):
        overlay = make_overlay()

        width, height = overlay._target_size()

        self.assertEqual(width, 460)
        self.assertEqual(height, 310)
        self.assertLess(width, 540)
        self.assertLess(height, 430)

    def test_overlay_target_size_is_bounded_on_small_screen(self):
        overlay = make_overlay(width=430, height=320)

        width, height = overlay._target_size()

        self.assertEqual(width, 406)
        self.assertEqual(height, 272)

    def test_default_overlay_target_size_is_consistent_regardless_of_compact(self):
        overlay = make_overlay()

        self.assertEqual(overlay._target_size(), (460, 310))

        overlay.is_compact = True
        self.assertEqual(overlay._target_size(), (460, 310))

    def test_startup_overlay_target_size_allows_loading_copy(self):
        overlay = make_overlay()
        overlay.placement = "startup"

        width, height = overlay._target_size()

        self.assertEqual(width, 580)
        self.assertEqual(height, 172)
        self.assertGreater(overlay._text_wraplength(), 500)

    def test_startup_overlay_target_size_is_bounded_on_small_screen(self):
        overlay = make_overlay(width=430, height=320)
        overlay.placement = "startup"

        width, height = overlay._target_size()

        self.assertEqual(width, 406)
        self.assertEqual(height, 172)
        self.assertLessEqual(overlay._text_wraplength(), width)

    def test_show_applies_compact_and_startup_placement(self):
        overlay = make_overlay()
        fake_window = FakeShowWindow()
        render_calls = []
        position_calls = []
        overlay._ensure_window = lambda: setattr(overlay, "window", fake_window)
        overlay._render = lambda: render_calls.append("render")
        overlay._position_window = lambda: position_calls.append("position")

        overlay.show(
            caption="Preparing app",
            compact=True,
            placement="startup",
        )

        self.assertTrue(overlay.is_compact)
        self.assertEqual(overlay.placement, "startup")
        self.assertEqual(overlay.caption_text, "Preparing app")
        self.assertEqual(render_calls, ["render"])
        self.assertEqual(position_calls, ["position"])
        self.assertEqual(fake_window.deiconified, 1)
        self.assertEqual(fake_window.lifted, 1)

    def test_toggle_compact_updates_layout_state_without_hiding_window(self):
        overlay = make_overlay()
        overlay.window = FakeGeometryWindow()
        overlay.is_compact = True
        render_calls = []
        position_calls = []
        overlay._render = lambda: render_calls.append("render")
        overlay._position_window = lambda: position_calls.append("position")

        overlay.toggle_compact()

        self.assertFalse(overlay.is_compact)
        self.assertFalse(overlay.config.get("overlay_compact"))
        self.assertEqual(render_calls, ["render"])
        self.assertEqual(position_calls, ["position"])

    def test_very_long_caption_uses_smaller_subtitle_font_and_more_height(self):
        overlay = make_overlay()
        overlay.is_compact = False
        overlay.caption_text = " ".join(
            [
                "A long translated subtitle should remain readable inside the overlay"
                for _ in range(80)
            ]
        )

        _width, height = overlay._target_size()

        self.assertGreater(height, 220)
        self.assertLessEqual(height, overlay.root.winfo_screenheight() - 48)
        self.assertLess(overlay._effective_caption_font_size(), overlay.font_size)

    def test_legacy_large_default_font_migrates_to_subtitle_profile(self):
        config = FakeConfig()
        config.values.pop("overlay_font_profile")
        config.values["overlay_font_size"] = 24

        overlay = SubtitleOverlay(FakeRoot(), config, lambda: None, {})

        self.assertEqual(overlay.font_size, 16)
        self.assertEqual(config.get("overlay_font_profile"), "subtitle_v3")

    def test_previous_subtitle_profile_default_migrates_to_smaller_startup_font(self):
        config = FakeConfig()
        config.values["overlay_font_profile"] = "subtitle_v2"
        config.values["overlay_font_size"] = 18

        overlay = SubtitleOverlay(FakeRoot(), config, lambda: None, {})

        self.assertEqual(overlay.font_size, 16)
        self.assertEqual(config.get("overlay_font_profile"), "subtitle_v3")

    def test_saved_position_is_clamped_to_visible_screen_area(self):
        overlay = make_overlay()
        overlay.config.set("overlay_x", -100)
        overlay.config.set("overlay_y", 720)

        x, y = overlay._saved_or_default_position(width=700, height=250)

        self.assertEqual(x, 12)
        self.assertLessEqual(y, 768 - 250 - 12)
        self.assertGreaterEqual(y, 12)

    def test_default_subtitle_position_sits_above_bottom_margin(self):
        overlay = make_overlay()
        overlay.is_compact = False

        width, height = overlay._target_size()
        x, y = overlay._saved_or_default_position(width=width, height=height)

        self.assertEqual(x, (1366 - width) // 2)
        self.assertLessEqual(y, 768 - height - 124)

    def test_startup_placement_uses_top_right_without_saved_position(self):
        overlay = make_overlay()
        overlay.placement = "startup"
        overlay.config.set("overlay_x", 100)
        overlay.config.set("overlay_y", 720)

        x, y = overlay._saved_or_default_position(width=580, height=116)

        self.assertEqual(x, 1366 - 580 - 28)
        self.assertEqual(y, 42)

    def test_loading_label_animates_when_progress_is_indeterminate(self):
        overlay = make_overlay()
        overlay.loading_text = "Preparing model"
        overlay.loading_progress = None

        self.assertEqual(overlay._loading_label_text(), "Preparing model.")
        overlay.loading_animation_phase = 8
        self.assertEqual(overlay._loading_label_text(), "Preparing model...")

    def test_loading_label_shows_progress_percent_when_available(self):
        overlay = make_overlay()
        overlay.loading_text = "Downloading model"
        overlay.loading_progress = 0.42

        self.assertEqual(overlay._loading_label_text(), "Downloading model 42%")

    def test_repeated_subtitle_loading_update_does_not_rebuild_overlay(self):
        overlay = make_overlay()
        overlay.window = FakeWindow()
        overlay.is_compact = False
        overlay.status_state = "busy"
        overlay.loading_text = "Preparing model"
        overlay.loading_label = object()
        render_calls = []
        position_calls = []
        overlay._render = lambda: render_calls.append("render")
        overlay._position_window = lambda: position_calls.append("position")
        overlay._sync_existing_loading_widgets = lambda: None
        overlay._start_loading_animation = lambda: None

        overlay.set_loading("Preparing model", 0.4)

        self.assertEqual(render_calls, [])
        self.assertEqual(position_calls, [])

    def test_repeated_position_with_same_geometry_does_not_force_redraw(self):
        overlay = make_overlay()
        overlay.window = FakeGeometryWindow()
        overlay.is_compact = False
        overlay.caption_text = "Stable caption."

        overlay._position_window()
        overlay._position_window()

        self.assertEqual(len(overlay.window.geometry_calls), 1)
        self.assertEqual(overlay.window.update_calls, 1)

    def test_subtitle_layout_position_updates_are_debounced(self):
        root = SchedulingRoot()
        overlay = SubtitleOverlay(root, FakeConfig(), lambda: None, {})
        overlay.window = FakeGeometryWindow()
        overlay.is_compact = False

        overlay._request_position_window()
        overlay._request_position_window()

        self.assertEqual(len(root.after_calls), 1)
        _job, _delay_ms, callback = root.after_calls[0]
        callback()

        self.assertEqual(len(overlay.window.geometry_calls), 1)

    def test_first_subtitle_loading_update_builds_loading_widgets(self):
        overlay = make_overlay()
        overlay.window = FakeWindow()
        overlay.is_compact = False
        render_calls = []
        overlay._render = lambda: render_calls.append("render")
        overlay._position_window = lambda: None
        overlay._start_loading_animation = lambda: None

        overlay.set_loading("Preparing model", None)

        self.assertEqual(render_calls, ["render"])

    def test_loading_state_disables_related_overlay_actions(self):
        overlay = make_overlay()
        overlay.actions["get_state"] = lambda: {
            "model_download_in_progress": True,
        }

        controls = overlay._control_flags()

        self.assertTrue(controls["recognition_action_disabled"])
        self.assertTrue(controls["input_language_disabled"])
        self.assertTrue(controls["output_language_disabled"])
        self.assertTrue(controls["transcript_actions_disabled"])

    def test_offline_translation_loading_disables_related_overlay_actions(self):
        overlay = make_overlay()
        overlay.actions["get_state"] = lambda: {
            "offline_translation_prepare_in_progress": True,
        }

        controls = overlay._control_flags()

        self.assertTrue(controls["recognition_action_disabled"])
        self.assertTrue(controls["input_language_disabled"])
        self.assertTrue(controls["output_language_disabled"])
        self.assertTrue(controls["transcript_actions_disabled"])

    def test_live_state_keeps_unrelated_overlay_actions_available(self):
        overlay = make_overlay()
        overlay.is_running = True
        overlay.actions["get_state"] = lambda: {
            "status": "live",
            "is_recognizing": True,
        }

        controls = overlay._control_flags()

        self.assertFalse(controls["recognition_action_disabled"])
        self.assertFalse(controls["input_language_disabled"])
        self.assertFalse(controls["output_language_disabled"])
        self.assertFalse(controls["transcript_actions_disabled"])

    def test_language_switch_disables_all_overlay_actions(self):
        overlay = make_overlay()
        overlay.actions["get_state"] = lambda: {
            "language_switch_in_progress": True,
        }

        controls = overlay._control_flags()

        self.assertTrue(controls["recognition_action_disabled"])
        self.assertTrue(controls["input_language_disabled"])
        self.assertTrue(controls["output_language_disabled"])
        self.assertTrue(controls["transcript_actions_disabled"])


if __name__ == "__main__":
    unittest.main()
