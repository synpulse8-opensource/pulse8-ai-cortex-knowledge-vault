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


class TestRegexMasking:
    """Deliverable 2: Apply deterministic regex patterns from parsed rules."""

    def _load(self, tmp_vault: Path):
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        rules = masker.load_rules()
        return masker, rules

    def test_masks_client_names(self, tmp_vault: Path):
        """Regex should replace client names with [CLIENT NAMES]."""
        masker, rules = self._load(tmp_vault)
        text = "We signed a deal with Acme Corp last week."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "Acme Corp" not in masked
        assert "[CLIENT NAMES]" in masked
        assert count >= 1

    def test_masks_client_name_variant(self, tmp_vault: Path):
        """Regex should also match 'Acme Corporation'."""
        masker, rules = self._load(tmp_vault)
        text = "Acme Corporation delivered the project."
        masked, _ = masker.apply_regex_rules(text, rules)
        assert "Acme Corporation" not in masked
        assert "[CLIENT NAMES]" in masked

    def test_masks_financial_figures(self, tmp_vault: Path):
        """Regex should replace dollar amounts."""
        masker, rules = self._load(tmp_vault)
        text = "The contract was worth $1,500,000.00 in total."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "$1,500,000.00" not in masked
        assert "[FINANCIAL FIGURES]" in masked
        assert count >= 1

    def test_masks_project_codes(self, tmp_vault: Path):
        """Regex should replace PRJ-XXXXX codes."""
        masker, rules = self._load(tmp_vault)
        text = "PRJ-12345 is on track. Project Phoenix starts next month."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "PRJ-12345" not in masked
        assert "Project Phoenix" not in masked
        assert count >= 2

    def test_no_match_returns_original(self, tmp_vault: Path):
        """If no patterns match, the text should be unchanged."""
        masker, rules = self._load(tmp_vault)
        text = "This text has no sensitive content."
        masked, count = masker.apply_regex_rules(text, rules)
        assert masked == text
        assert count == 0

    def test_multiple_matches_in_same_text(self, tmp_vault: Path):
        """Multiple occurrences of the same pattern should all be masked."""
        masker, rules = self._load(tmp_vault)
        text = "Acme Corp paid Wayne Enterprises $500.00 for PRJ-9999."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "Acme Corp" not in masked
        assert "Wayne Enterprises" not in masked
        assert "$500.00" not in masked
        assert "PRJ-9999" not in masked
        assert count >= 4

    def test_invalid_regex_skipped_gracefully(self, tmp_vault: Path):
        """An invalid regex pattern should be skipped without crashing."""
        from cortex.compiler.masking import ContentMasker, MaskingRule, MaskingRules

        rules = MaskingRules(
            rules=[MaskingRule(category="Bad", description="broken", patterns=["[invalid"])],
            raw_markdown="",
        )
        masker = ContentMasker(tmp_vault)
        masked, count = masker.apply_regex_rules("some text", rules)
        assert masked == "some text"
        assert count == 0

    def test_taiwan_national_id_masked(self):
        """Taiwan national ID pattern should mask e.g. A123456789."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "Customer ID: A123456789, please verify."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "A123456789" not in masked
        assert count >= 1

    def test_taiwan_phone_masked(self):
        """Taiwan mobile phone pattern should mask 09xx-xxx-xxx."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "Contact: 0912-345-678 for details."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "0912-345-678" not in masked
        assert count >= 1

    def test_taiwan_ntd_amount_masked(self):
        """NT$ amounts should be masked."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "Loan amount: NT$2,500,000.00 approved."
        masked, count = masker.apply_regex_rules(text, rules)
        assert "NT$2,500,000.00" not in masked
        assert count >= 1
