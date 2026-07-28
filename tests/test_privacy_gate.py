import unittest
from pathlib import Path

from scripts.privacy_gate import scan_text, unsafe_name


class PrivacyGateTests(unittest.TestCase):
    def test_safe_public_text_passes(self) -> None:
        self.assertEqual(
            scan_text(Path("README.md"), "https://github.com/example/project\nrelative/file.rs\n"),
            [],
        )

    def test_task_hyphens_do_not_look_like_credentials(self) -> None:
        self.assertEqual(scan_text(Path("README.md"), "task-requirement\nrisk-aware\n"), [])

    def test_credential_prefix_requires_a_token_shaped_value(self) -> None:
        token = "s" + "k-" + "abcdefgh123456"
        self.assertEqual(scan_text(Path("sample"), token), [("credential prefix", 1)])


    def test_contact_and_host_path_are_detected_without_echoing_values(self) -> None:
        email = "person" + "@" + "example.invalid"
        host_path = "C:" + chr(92) + "private" + chr(92) + "file.txt"
        labels = {label for label, _ in scan_text(Path("sample"), email + "\n" + host_path)}
        self.assertEqual(labels, {"email address", "Windows absolute path"})

    def test_credential_like_name_is_rejected(self) -> None:
        self.assertEqual(unsafe_name(Path(".env")), "credential-like filename")
        self.assertEqual(unsafe_name(Path("signing.pem")), "credential-like file suffix")

    def test_replacement_character_is_rejected(self) -> None:
        findings = scan_text(Path("sample"), "prefix" + chr(0xFFFD) + "suffix")
        self.assertEqual(findings, [("replacement character", 1)])


if __name__ == "__main__":
    unittest.main()
