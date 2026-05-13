"""Tests for content masking during ingestion."""
from __future__ import annotations

from pathlib import Path


SAMPLE_RULES_MD = """\
# Content Masking Rules

These rules are applied to all ingested content before compilation.

## Client Names

Replace all client and customer names with anonymized placeholders.
Use the format `[CLIENT-A]`, `[CLIENT-B]`, etc.

### Patterns
- `Acme Corp(oration)?`
- `Wayne Enterprises`

## Financial Figures

Mask monetary amounts. Replace with `[AMOUNT]`.

### Patterns
- `\\$[\\d,]+(\\.\\d{2})?`

## Internal Project Codes

Replace project codes with `[PROJECT-X]`.

### Patterns
- `PRJ-\\d{4,6}`
- `Project (Phoenix|Titan)`

## No Patterns Section

This category has a description but no regex patterns.
The LLM should handle it contextually.
"""


class TestParseMaskingRules:
    """Deliverable 1: Parse .cortex/masking-rules.md into MaskingRules."""

    def test_load_rules_returns_masking_rules(self, tmp_vault: Path):
        """load_rules should return a MaskingRules dataclass."""
        from cortex.compiler.masking import ContentMasker, MaskingRules

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        assert isinstance(rules, MaskingRules)

    def test_load_rules_parses_categories(self, tmp_vault: Path):
        """Each ## section should become a MaskingRule with the heading as category."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        categories = [r.category for r in rules.rules]
        assert "Client Names" in categories
        assert "Financial Figures" in categories
        assert "Internal Project Codes" in categories
        assert "No Patterns Section" in categories

    def test_load_rules_extracts_patterns(self, tmp_vault: Path):
        """Regex patterns under ### Patterns should be extracted as a list."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        client_rule = next(r for r in rules.rules if r.category == "Client Names")
        assert len(client_rule.patterns) == 2
        assert "Acme Corp(oration)?" in client_rule.patterns
        assert "Wayne Enterprises" in client_rule.patterns

    def test_load_rules_extracts_description(self, tmp_vault: Path):
        """The natural language body between ## heading and ### Patterns should be the description."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        client_rule = next(r for r in rules.rules if r.category == "Client Names")
        assert "anonymized placeholders" in client_rule.description

    def test_load_rules_section_without_patterns(self, tmp_vault: Path):
        """A section without ### Patterns should have an empty patterns list."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        no_pat = next(r for r in rules.rules if r.category == "No Patterns Section")
        assert no_pat.patterns == []
        assert "LLM should handle" in no_pat.description

    def test_load_rules_stores_raw_markdown(self, tmp_vault: Path):
        """MaskingRules should store the full raw markdown for LLM context."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        assert rules.raw_markdown == SAMPLE_RULES_MD

    def test_load_rules_missing_file_returns_none(self, tmp_vault: Path):
        """When the rules file doesn't exist, load_rules should return None."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        assert rules is None

    def test_load_rules_empty_file_returns_none(self, tmp_vault: Path):
        """When the rules file exists but has no ## sections, load_rules returns None."""
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(
            "# Content Masking Rules\n\nNo sections here.\n"
        )
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        assert rules is None

    def test_taiwan_banking_rules_file_parses(self):
        """The example_vault Taiwan banking PII rules file should parse correctly."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        assert rules is not None
        categories = [r.category for r in rules.rules]
        assert "National ID Numbers" in categories
        assert "Bank Account Numbers" in categories
        assert "Credit Card Numbers" in categories
        assert "Phone Numbers" in categories
        assert "Customer Names" in categories
        assert "Income and Financial Amounts" in categories
        nid = next(r for r in rules.rules if r.category == "National ID Numbers")
        assert len(nid.patterns) == 1
        assert nid.patterns[0] == r"[A-Z][12]\d{8}"
