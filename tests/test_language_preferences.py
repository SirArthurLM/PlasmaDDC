"""Language behavior and UI checks, without monitor access or user config writes."""

import os
from pathlib import Path
from string import Formatter
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLocale, QSettings
from PySide6.QtWidgets import QApplication, QDialog

import app
import i18n
from backend import MonitorProfile, MonitorSummary, VCPValue, normalize_percent


class LanguageResolutionTests(unittest.TestCase):
    def test_system_locale_and_english_fallback(self):
        for locale_name, expected in [
            ("es_ES", "es"),
            ("es-MX", "es"),
            ("es", "es"),
            ("en_GB", "en"),
            ("sv_SE", "en"),
            ("C", "en"),
            ("", "en"),
        ]:
            with self.subTest(locale_name=locale_name):
                self.assertEqual(i18n.resolve_language("system", locale_name), expected)

    def test_explicit_language_overrides_locale(self):
        self.assertEqual(i18n.resolve_language("en", "es_ES"), "en")
        self.assertEqual(i18n.resolve_language("es", "sv_SE"), "es")

    def test_unknown_saved_preference_recovers_to_system(self):
        manager = i18n.LanguageManager()
        manager.configure("unknown", "es_MX")
        self.assertEqual(manager.preference, "system")
        self.assertEqual(manager.language, "es")
        self.assertEqual(manager.translate("Apply"), "Aplicar")
        self.assertEqual(manager.translate("Uncatalogued message"), "Uncatalogued message")

    def test_backend_messages_follow_selected_language(self):
        manager = i18n.LanguageManager()
        with patch("i18n.language_manager", manager):
            manager.configure("es", "en_US")
            self.assertEqual(VCPValue(0x62, supported=False).as_text(), "0x62: no soportado")
            with self.assertRaisesRegex(ValueError, "valor debe estar entre"):
                normalize_percent(101)
            manager.configure("en", "es_ES")
            self.assertEqual(VCPValue(0x62, supported=False).as_text(), "0x62: unsupported")

    def test_catalog_preserves_format_placeholders(self):
        formatter = Formatter()

        def fields(message):
            return sorted(
                (field, spec, conversion)
                for _, field, spec, conversion in formatter.parse(message)
                if field is not None
            )

        for english, spanish in i18n.SPANISH.items():
            with self.subTest(message=english):
                self.assertEqual(fields(english), fields(spanish))


class LanguagePreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings_path = str(Path(self.temp.name) / "preferences.ini")
        self.make_settings = lambda *args: QSettings(settings_path, QSettings.IniFormat)
        self.manager = i18n.LanguageManager()
        self.backend = Mock()
        monitors = [
            MonitorSummary(
                i, i + 1, i + 10, f"/dev/i2c-{i + 10}", None, "GSM", f"LG {i}", None, f"LG {i}"
            )
            for i in range(2)
        ]
        self.backend.refresh_monitors.return_value = monitors
        self.backend.build_monitor_profile.side_effect = lambda index: MonitorProfile(
            monitors[index],
            values={
                "volume": VCPValue(0x62, "Audio speaker volume", 50, 100),
                "brightness": VCPValue(0x10, "Brightness", 80, 100),
            },
        )
        self.patches = [
            patch("app.QSettings", self.make_settings),
            patch("app.QLocale.system", return_value=QLocale("sv_SE")),
            patch("app.PlasmaDDCBackend", return_value=self.backend),
            patch("app.language_manager", self.manager),
            patch("i18n.language_manager", self.manager),
        ]
        for item in self.patches:
            item.start()
        self.window = app.MainWindow()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.application.processEvents()
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_switches_live_preserves_selection_and_persists(self):
        self.window.sidebar.setCurrentRow(3)
        self.window.monitor_combo.setCurrentIndex(1)
        self.window.set_language_preference("es")
        self.assertEqual(self.window.volume_control.apply_button.text(), "Aplicar")
        self.assertEqual(self.window.sidebar.item(0).text(), "Resumen")
        self.assertEqual(self.window.sidebar.currentRow(), 3)
        self.assertEqual(self.window.current_monitor_index(), 1)
        self.assertEqual(self.make_settings().value("language"), "es")
        self.backend.set_volume.assert_not_called()
        self.backend.set_brightness.assert_not_called()
        other = app.MainWindow()
        self.assertEqual(other.volume_control.read_button.text(), "Leer")
        other.close()
        other.deleteLater()
        self.window.set_language_preference("en")
        self.assertEqual(self.window.volume_control.apply_button.text(), "Apply")
        self.assertEqual(self.window.sidebar.item(0).text(), "Overview")
        self.assertEqual(self.window.sidebar.currentRow(), 3)

    def test_system_default_uses_spanish_locale(self):
        with patch("app.QLocale.system", return_value=QLocale("es_MX")):
            self.window.set_language_preference("es")
            self.window.set_language_preference("system")
        self.assertEqual(self.manager.language, "es")
        self.assertEqual(self.make_settings().value("language"), "system")
        self.assertEqual(self.window.sidebar.item(1).text(), "Imagen")

    def test_dialog_choices_and_cancel(self):
        dialog = app.LanguagePreferencesDialog(self.window)
        self.assertEqual(
            [dialog.language_combo.itemData(i) for i in range(3)],
            ["system", "en", "es"],
        )
        dialog.language_combo.setCurrentIndex(2)
        self.assertEqual(dialog.selected_language(), "es")
        dialog.reject()
        with (
            patch("app.LanguagePreferencesDialog", return_value=dialog),
            patch.object(dialog, "exec", return_value=QDialog.Rejected),
        ):
            self.window.show_language_preferences()
        self.assertEqual(self.manager.preference, "system")
        self.assertFalse(self.make_settings().contains("language"))
        dialog.deleteLater()

    def test_accepting_dialog_applies_choice(self):
        dialog = Mock()
        dialog.exec.return_value = QDialog.Accepted
        dialog.selected_language.return_value = "es"
        with patch("app.LanguagePreferencesDialog", return_value=dialog):
            self.window.show_language_preferences()
        self.assertEqual(self.window.volume_control.name_label.text(), "Volumen")
        self.assertEqual(self.make_settings().value("language"), "es")

    def test_no_monitor_state_can_be_retranslated(self):
        self.window.monitors = []
        self.window.set_language_preference("es")
        self.assertEqual(self.window.overview_label.text(), "No se han detectado monitores.")
        self.assertFalse(self.window.volume_control.isEnabled())


if __name__ == "__main__":
    unittest.main()
