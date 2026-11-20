"""Regression checks for text decoding and partial advanced diagnostic output.

None of these tests accesses a monitor or runs ddcutil itself.
"""

import subprocess
import sys
import unittest
from unittest.mock import patch

from backend import (
    DDCUtilCommandError,
    DDCUtilRunner,
    DDCPermissionError,
    PlasmaDDCBackend,
    PlasmaDDCError,
    VCPUnsupportedError,
)
from i18n import language_manager


class DiagnosticBackendChecks(unittest.TestCase):
    def setUp(self):
        language_manager.configure("en", "en_US")

    def tearDown(self):
        language_manager.configure("system", "en_US")

    def runner(self):
        runner = DDCUtilRunner()
        runner.path = sys.executable  # Only invoke Python, never ddcutil.
        return runner

    def test_non_utf8_bytes_in_capabilities_do_not_crash(self):
        runner = self.runner()
        output = runner.run("-c", ["import sys; sys.stdout.buffer.write(b'cap: \\xbe')"])
        self.assertEqual(output, r"cap: \xbe")

    def test_valid_utf8_output_is_preserved(self):
        runner = self.runner()
        output = runner.run("-c", ["print('6500 K – pantalla')"])
        self.assertEqual(output, "6500 K – pantalla")

    def test_nonzero_exit_code_and_output_remain_available(self):
        runner = self.runner()
        with self.assertRaises(DDCUtilCommandError) as caught:
            runner.run("-c", ["import sys; print('VCP code 0x10'); sys.exit(7)"])
        self.assertEqual(caught.exception.output, "VCP code 0x10")
        self.assertEqual(caught.exception.returncode, 7)

    def test_unsupported_bulk_feature_preserves_output_and_exit_status(self):
        runner = self.runner()
        statement = "import sys; print('Unsupported feature code: 0xAB'); sys.exit(4)"
        with self.assertRaises(DDCUtilCommandError) as diagnostic:
            runner.run("-c", [statement], preserve_partial_output=True)
        self.assertEqual(diagnostic.exception.returncode, 4)
        self.assertIn("Unsupported feature", diagnostic.exception.output)
        with self.assertRaises(VCPUnsupportedError):
            runner.run("-c", [statement])  # Regular operations retain normal errors.

    def test_getvcp_all_partial_output_is_not_a_modal_error(self):
        backend = PlasmaDDCBackend()
        with patch.object(backend, "_ddc_select", return_value={}), patch.object(
            backend.ddcutil, "get_vcp_all",
            side_effect=DDCUtilCommandError("VCP code 0x10: 100", 9),
        ) as call:
            output = backend.get_all_vcps_text(0)
        call.assert_called_once_with()
        self.assertIn("code 9", output)
        self.assertIn("may be incomplete", output)
        self.assertIn("VCP code 0x10: 100", output)

    def test_capabilities_partial_output_is_labeled(self):
        backend = PlasmaDDCBackend()
        with patch.object(backend, "_ddc_select", return_value={}), patch.object(
            backend.ddcutil, "capabilities",
            side_effect=DDCUtilCommandError("vcp(10 12 14)", 6),
        ) as call:
            output = backend.get_capabilities_text(0)
        call.assert_called_once_with()
        self.assertIn("code 6", output)
        self.assertIn("vcp(10 12 14)", output)

    def test_no_output_does_not_disguise_failure(self):
        backend = PlasmaDDCBackend()
        with patch.object(backend, "_ddc_select", return_value={}), patch.object(
            backend.ddcutil, "get_vcp_all",
            side_effect=PlasmaDDCError("ddcutil failed without output"),
        ):
            with self.assertRaises(PlasmaDDCError):
                backend.get_all_vcps_text(0)

    def test_permission_errors_remain_errors(self):
        backend = PlasmaDDCBackend()
        with patch.object(backend, "_ddc_select", return_value={}), patch.object(
            backend.ddcutil, "capabilities",
            side_effect=DDCPermissionError("Permission denied"),
        ):
            with self.assertRaises(DDCPermissionError):
                backend.get_capabilities_text(0)


if __name__ == "__main__":
    unittest.main()
