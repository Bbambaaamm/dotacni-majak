import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _headings(md: str) -> list[str]:
    """Return normalized lowercase ATX headings (level 2+ only)."""
    out = []
    for line in md.splitlines():
        m = re.match(r"^#{2,}\s+(.*)$", line)
        if m:
            out.append(m.group(1).strip().lower())
    return out


class SecurityPolicyTest(unittest.TestCase):
    """
    Issue #432 — SECURITY.md, vulnerability disclosure a incident contact.

    Kontrola, že kořenový SECURITY.md obsahuje všechny požadované sekce a
    neobsahuje placeholder/raw secret contact informace (fail-closed).
    """

    @classmethod
    def setUpClass(cls):
        cls.policy = _read(ROOT / "SECURITY.md")
        cls.headings = _headings(cls.policy)

    # --- existence
    def test_security_policy_exists_at_repo_root(self):
        self.assertTrue((ROOT / "SECURITY.md").is_file())

    # --- required sections (issue acceptance criteria)
    def test_contains_reporting_section(self):
        self.assertTrue(
            any("hlášení" in h or "reporting" in h for h in self.headings),
            f"SECURITY.md musí mít sekci o nahlášení; hlavičny: {self.headings}",
        )

    def test_contains_supported_versions(self):
        self.assertTrue(
            any("podporované verze" in h or "supported versions" in h for h in self.headings),
            "SECURITY.md musí uvádět podporované verze.",
        )

    def test_contains_severity_triage(self):
        # Severity rating + triage workflow must be described
        self.assertTrue(
            any("severity" in h or "sledování" in h or "stupeň" in h for h in self.headings),
            "SECURITY.md musí mít sekci severity/triage.",
        )
        self.assertTrue(
            any("triáž" in h or "workflow" in h for h in self.headings),
            "SECURITY.md musí popisovat triage workflow.",
        )

    def test_contains_embargo_disclosure(self):
        self.assertTrue(
            any("embargo" in h or "koordinované zveřejnění" in h for h in self.headings),
            "SECURITY.md musí definovat embargo/coordinated disclosure.",
        )

    def test_contains_negative_abuse_scenarios(self):
        self.assertTrue(
            any("negative" in h or "abuse" in h or "zneužití" in h for h in self.headings),
            "SECURITY.md musí zahrnovat negative/abuse scénáře.",
        )

    def test_contains_fail_closed_definition(self):
        self.assertTrue(
            any("fail-closed" in h or "degraded" in h or "bezpečný degraded" in h for h in self.headings),
            "SECURITY.md musí definovat fail-closed / bezpečný degraded stav.",
        )

    def test_contains_secrets_not_in_logs(self):
        self.assertTrue(
            any("secrets" in h or "logu" in h or "log redaction" in h for h in self.headings),
            "SECURITY.md musí popisovat, že secrets/PII nejsou v logu.",
        )

    def test_contains_runbook_reference(self):
        self.assertTrue(
            any("runbook" in h or "dokumentace" in h or "runbook & dokumentace" in h for h in self.headings),
            "SECURITY.md musí odkazovat na runbook/dokumentaci.",
        )

    def test_contains_release_gate_reference(self):
        self.assertTrue(
            any("release gate" in h or "release gate" in h for h in self.headings),
            "SECURITY.md musí jasně definovat release gate.",
        )

    def test_contains_residual_risks(self):
        self.assertTrue(
            any("residual" in h or "známá omezení" in h for h in self.headings),
            "SECURITY.md musí dokumentovat residual risks.",
        )

    # --- severity levels referenced
    def test_severity_levels_are_documented(self):
        for sev in ("sev-1", "sev-2", "sev-3"):
            self.assertIn(
                sev, self.policy.lower(),
                f"SECURITY.md musí popisovat {sev.upper()}.",
            )

    # --- fail-closed / degraded references resolve to real docs
    def test_references_existing_runbook(self):
        self.assertIn("docs/RUNBOOK.md", self.policy)
        self.assertTrue((ROOT / "docs" / "RUNBOOK.md").is_file())

    def test_references_existing_threat_model(self):
        self.assertIn("docs/SECURITY.md", self.policy)
        self.assertTrue((ROOT / "docs" / "SECURITY.md").is_file())

    def test_references_existing_release_gate(self):
        self.assertTrue(
            any(
                "docs/V1_RELEASE_GATE.md" in line
                for line in self.policy.splitlines()
            ),
            "SECURITY.md musí odkazovat na docs/V1_RELEASE_GATE.md.",
        )
        self.assertTrue((ROOT / "docs" / "V1_RELEASE_GATE.md").is_file())

    # --- negative/abuse: no fake/raw contact secret (fail-closed)
    def test_does_not_harden_unverified_private_email(self):
        """
        Fail-closed: dokument nesmí obsahovat konkrétní emailovou adresu
        určenou jako security contact, dokud není verifikovaná. GitHub
        Security Advisories je primárním kanálem — e-mail může být pouze
        jako dokumentovaný fallback s explicitní výstrahou.
        """
        emails = re.findall(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", self.policy, re.I)
        # If an email appears, it must be inside an explicitly-flagged fallback
        # sentence — never as a primary/standalone contact claim.
        if emails:
            for email in emails:
                idx = self.policy.index(email)
                window = self.policy[max(0, idx - 400): idx + 400].lower()
                self.assertTrue(
                    "fallback" in window or "záložní" in window or "dočasn" in window,
                    f"SECURITY.md obsahuje neověřený kontaktní e-mail {email} "
                    f"mimo fallback — fail-closed.",
                )

    def test_does_not_contain_placeholder_secret(self):
        """Žádný placeholder typu 'YOUR_SECRET' / 'YOUR_EMAIL_HERE' v contact sekcích."""
        lowered = self.policy.lower()
        for marker in ("your_secret", "your_email", "placeholder", "your-email", "todo"):
            self.assertNotIn(
                marker, lowered,
                f"SECURITY.md nesmí obsahovat placeholder '{marker}'.",
            )

    # --- abuse: automated scanner reports must be rejected
    def test_automated_scanner_reports_are_rejected(self):
        lowered = self.policy.lower()
        # Dokument musí explicitně uvádět, že nevalidované reporty ze šcannerů
        # jsou zamítány (nezajímají se za security incident).
        self.assertTrue(
            "šcanner" in lowered or "scanner" in lowered,
            "SECURITY.md musí vymínit šcanner/strojové reporty.",
        )
        # Musí být někde přirozeně upozorněno, že takové reporty jsou odmítnuty.
        self.assertTrue(
            "zamít" in lowered or "odmít" in lowered,
            "SECURITY.md musí explicitně odmítat nevalidované scanner reporty.",
        )

    # --- private reporting mechanism is named (not blank)
    def test_naming_github_private_vulnerability_reporting(self):
        lowered = self.policy.lower()
        self.assertTrue(
            "private vulnerability reporting" in lowered or "report a vulnerability" in lowered,
            "SECURITY.md musí vymínit GitHub Private vulnerability reporting jako primární kanál.",
        )


if __name__ == "__main__":
    unittest.main()
