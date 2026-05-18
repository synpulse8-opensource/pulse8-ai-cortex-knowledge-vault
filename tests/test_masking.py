"""Tests for content masking during ingestion."""
from __future__ import annotations

from pathlib import Path

import pytest


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

    def test_taiwan_name_spelling_three_chars_masked(self):
        """Chinese name spelled out character-by-character (3 chars) should be masked."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "我的名字是林木的林，美麗的美，惠顧的惠，請幫我查詢帳戶。"
        masked, count = masker.apply_regex_rules(text, rules)
        assert "林木的林，美麗的美，惠顧的惠" not in masked
        assert "[CUSTOMER NAMES]" in masked
        assert count >= 1

    def test_taiwan_name_spelling_english_comma_masked(self):
        """Name spelling with English commas should also be masked."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "我叫林木的林,美麗的美,惠顧的惠。"
        masked, count = masker.apply_regex_rules(text, rules)
        assert "林木的林,美麗的美,惠顧的惠" not in masked
        assert "[CUSTOMER NAMES]" in masked
        assert count >= 1

    def test_taiwan_name_spelling_no_false_positive(self):
        """Normal Chinese text with 的 should not be falsely matched."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "美麗的風景和壯觀的山脈，令人讚嘆。"
        masked, _ = masker.apply_regex_rules(text, rules)
        assert "[CUSTOMER NAMES]" not in masked


class TestPresidioMasking:
    """Presidio NER-based PII detection layer."""

    def test_apply_presidio_masking_detects_email(self, tmp_vault: Path):
        """Presidio should detect and mask email addresses."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        text = "Please contact john.doe@example.com for details."
        masked, count = masker.apply_presidio_masking(text)
        assert "john.doe@example.com" not in masked
        assert count >= 1

    def test_apply_presidio_masking_detects_phone(self, tmp_vault: Path):
        """Presidio should detect and mask phone numbers."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        text = "Call me at 212-555-5555 tomorrow."
        masked, count = masker.apply_presidio_masking(text)
        assert "212-555-5555" not in masked
        assert count >= 1

    def test_apply_presidio_masking_detects_person_name(self, tmp_vault: Path):
        """Presidio should detect English person names via NER."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        text = "The account belongs to John Smith, please verify."
        masked, count = masker.apply_presidio_masking(text)
        assert "John Smith" not in masked
        assert count >= 1

    def test_apply_presidio_masking_no_pii_unchanged(self, tmp_vault: Path):
        """Text without PII should remain unchanged."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        text = "The transformer architecture uses self-attention."
        masked, count = masker.apply_presidio_masking(text)
        assert masked == text
        assert count == 0


class TestPresidioCustomRecognizers:
    """Custom masking-rules.md patterns registered as Presidio recognizers."""

    def test_presidio_with_custom_rules_masks_taiwan_nid(self, tmp_vault: Path):
        """Taiwan national ID pattern from rules file should work as a Presidio recognizer."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "Customer ID: A123456789, please verify."
        masked, count = masker.apply_presidio_masking(text, rules=rules)
        assert "A123456789" not in masked
        assert count >= 1

    def test_presidio_with_custom_rules_masks_name_spelling(self, tmp_vault: Path):
        """Chinese name spelling pattern from rules should work as Presidio recognizer."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "我的名字是林木的林，美麗的美，惠顧的惠。"
        masked, count = masker.apply_presidio_masking(text, rules=rules)
        assert "林木的林，美麗的美，惠顧的惠" not in masked
        assert count >= 1

    def test_presidio_custom_rules_combined_with_builtin(self, tmp_vault: Path):
        """Custom rules + built-in Presidio recognizers should both fire."""
        from cortex.compiler.masking import ContentMasker

        vault = Path(__file__).resolve().parent.parent / "example_vault"
        masker = ContentMasker(vault)
        rules = masker.load_rules()
        text = "Contact john@example.com, NID: A123456789"
        masked, count = masker.apply_presidio_masking(text, rules=rules)
        assert "john@example.com" not in masked
        assert "A123456789" not in masked
        assert count >= 2


class TestLLMMasking:
    """Deliverable 3: LLM context-aware masking via apply_llm_masking."""

    @pytest.fixture()
    def _rules(self, tmp_vault: Path):
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        return masker, masker.load_rules()

    @pytest.mark.asyncio
    async def test_llm_masking_calls_api(self, _rules):
        """apply_llm_masking should call the LLM and return its response."""
        from unittest.mock import AsyncMock, MagicMock, patch

        masker, rules = _rules
        llm_output = "We signed a deal with [CLIENT NAMES] last week."
        choice = MagicMock()
        choice.message.content = llm_output
        response = MagicMock()
        response.choices = [choice]

        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.masking_model = ""
            mock_settings.compiler_model = "test-model"
            mock_settings.compiler_max_tokens = 4096
            with patch("cortex.compiler.masking.AsyncOpenAI") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=response)
                mock_client_cls.return_value = mock_client
                result = await masker.apply_llm_masking("original text", rules)

        assert result == llm_output

    @pytest.mark.asyncio
    async def test_llm_masking_skipped_without_api_key(self, _rules):
        """Without an API key, apply_llm_masking should return content unchanged."""
        from unittest.mock import patch

        masker, rules = _rules
        original = "Acme Corp data here."
        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            result = await masker.apply_llm_masking(original, rules)
        assert result == original

    @pytest.mark.asyncio
    async def test_llm_masking_falls_back_on_error(self, _rules):
        """If LLM call fails, apply_llm_masking should return content unchanged."""
        from unittest.mock import AsyncMock, MagicMock, patch

        masker, rules = _rules
        original = "Some sensitive text."
        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.masking_model = "test-model"
            mock_settings.compiler_max_tokens = 4096
            with patch("cortex.compiler.masking.AsyncOpenAI") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(
                    side_effect=Exception("API down")
                )
                mock_client_cls.return_value = mock_client
                result = await masker.apply_llm_masking(original, rules)
        assert result == original

    @pytest.mark.asyncio
    async def test_llm_masking_uses_masking_model_if_set(self, _rules):
        """When masking_model is set, it should be used instead of compiler_model."""
        from unittest.mock import AsyncMock, MagicMock, patch

        masker, rules = _rules
        choice = MagicMock()
        choice.message.content = "masked"
        response = MagicMock()
        response.choices = [choice]

        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.masking_model = "special-masking-model"
            mock_settings.compiler_model = "general-model"
            mock_settings.compiler_max_tokens = 4096
            with patch("cortex.compiler.masking.AsyncOpenAI") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=response)
                mock_client_cls.return_value = mock_client
                await masker.apply_llm_masking("text", rules)
                call_kwargs = mock_client.chat.completions.create.call_args
                assert call_kwargs.kwargs["model"] == "special-masking-model"


class TestMaskPipeline:
    """Deliverable 3 (continued): Full mask() pipeline combining regex + LLM."""

    @pytest.mark.asyncio
    async def test_mask_no_rules_file_passes_through(self, tmp_vault: Path):
        """mask() with no rules file should return content unchanged."""
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        result = await masker.mask("sensitive text")
        assert result.content == "sensitive text"
        assert result.applied_rules == 0
        assert result.llm_masking is False

    @pytest.mark.asyncio
    async def test_mask_regex_only_when_no_api_key(self, tmp_vault: Path):
        """mask() without API key should apply regex only, llm_masking=False."""
        from unittest.mock import patch
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_rules_path = ".cortex/masking-rules.md"
            result = await masker.mask("Acme Corp owes $100.00")
        assert "Acme Corp" not in result.content
        assert "$100.00" not in result.content
        assert result.applied_rules >= 2
        assert result.llm_masking is False

    @pytest.mark.asyncio
    async def test_mask_regex_plus_llm(self, tmp_vault: Path):
        """mask() with API key should apply regex then LLM, llm_masking=True."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)

        choice = MagicMock()
        choice.message.content = "Fully masked by LLM."
        response = MagicMock()
        response.choices = [choice]

        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = "test-key"
            mock_settings.llm_base_url = "https://test"
            mock_settings.masking_model = ""
            mock_settings.compiler_model = "test-model"
            mock_settings.compiler_max_tokens = 4096
            mock_settings.masking_rules_path = ".cortex/masking-rules.md"
            with patch("cortex.compiler.masking.AsyncOpenAI") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.chat.completions.create = AsyncMock(return_value=response)
                mock_client_cls.return_value = mock_client
                result = await masker.mask("Acme Corp owes $100.00")

        assert result.content == "Fully masked by LLM."
        assert result.llm_masking is True


    @pytest.mark.asyncio
    async def test_mask_pipeline_includes_presidio(self, tmp_vault: Path):
        """mask() should run Presidio NER to catch PII that regex rules miss."""
        from unittest.mock import patch
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        with patch("cortex.compiler.masking.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_rules_path = ".cortex/masking-rules.md"
            result = await masker.mask(
                "Contact john.doe@example.com about Acme Corp deal."
            )
        assert "john.doe@example.com" not in result.content
        assert "Acme Corp" not in result.content
        assert result.presidio_entities > 0


class TestRulesVersion:
    """Deliverable 6: rules_version computes SHA-256 of the rules file."""

    def test_rules_version_returns_hash(self, tmp_vault: Path):
        from cortex.compiler.masking import ContentMasker

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        version = masker.rules_version()
        assert version is not None
        assert version.startswith("sha256:")
        assert len(version) == len("sha256:") + 64

    def test_rules_version_none_when_missing(self, tmp_vault: Path):
        from cortex.compiler.masking import ContentMasker

        masker = ContentMasker(tmp_vault)
        assert masker.rules_version() is None

    def test_rules_version_changes_on_content_change(self, tmp_vault: Path):
        from cortex.compiler.masking import ContentMasker

        rules_path = tmp_vault / ".cortex" / "masking-rules.md"
        rules_path.write_text(SAMPLE_RULES_MD)
        masker = ContentMasker(tmp_vault)
        v1 = masker.rules_version()
        rules_path.write_text(SAMPLE_RULES_MD + "\n## Extra Rule\n\nMask extra.\n")
        v2 = masker.rules_version()
        assert v1 != v2


class TestCompilerMaskingIntegration:
    """Deliverable 5+6: masking step integrated into ingest_source."""

    @pytest.mark.asyncio
    async def test_ingest_applies_masking_when_enabled(self, tmp_vault: Path):
        """When masking_enabled=True, ingest_source should mask before enrichment."""
        import frontmatter as fm
        from unittest.mock import patch
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        (tmp_vault / "raw" / "sensitive.txt").write_text(
            "Acme Corp signed PRJ-12345 for $500.00."
        )
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_enabled = True
            mock_settings.masking_rules_path = ".cortex/masking-rules.md"
            mock_settings.masking_model = ""
            result = await compiler.ingest_source(tmp_vault / "raw" / "sensitive.txt")

        assert len(result) == 1
        post = fm.load(str(result[0]))
        assert "Acme Corp" not in post.content
        assert "PRJ-12345" not in post.content
        assert "$500.00" not in post.content

    @pytest.mark.asyncio
    async def test_ingest_skips_masking_when_disabled(self, tmp_vault: Path):
        """When masking_enabled=False, ingest_source should not mask."""
        import frontmatter as fm
        from unittest.mock import patch
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        (tmp_vault / "raw" / "sensitive.txt").write_text(
            "Acme Corp signed PRJ-12345 for $500.00."
        )
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_enabled = False
            result = await compiler.ingest_source(tmp_vault / "raw" / "sensitive.txt")

        post = fm.load(str(result[0]))
        assert "Acme Corp" in post.content

    @pytest.mark.asyncio
    async def test_ingest_records_masking_frontmatter(self, tmp_vault: Path):
        """When masking is applied, frontmatter should include masking_applied and masking_rules_version."""
        import frontmatter as fm
        from unittest.mock import patch
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / ".cortex" / "masking-rules.md").write_text(SAMPLE_RULES_MD)
        (tmp_vault / "raw" / "sensitive.txt").write_text(
            "Acme Corp data here."
        )
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_enabled = True
            mock_settings.masking_rules_path = ".cortex/masking-rules.md"
            mock_settings.masking_model = ""
            result = await compiler.ingest_source(tmp_vault / "raw" / "sensitive.txt")

        post = fm.load(str(result[0]))
        assert post.metadata.get("masking_applied") is True
        assert post.metadata.get("masking_rules_version", "").startswith("sha256:")

    @pytest.mark.asyncio
    async def test_ingest_no_masking_frontmatter_when_disabled(self, tmp_vault: Path):
        """When masking is disabled, frontmatter should not have masking fields."""
        import frontmatter as fm
        from unittest.mock import patch
        from cortex.compiler.compiler import KnowledgeCompiler

        (tmp_vault / "raw" / "plain.txt").write_text("Normal content.")
        compiler = KnowledgeCompiler(tmp_vault)

        with patch("cortex.compiler.compiler.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            mock_settings.masking_enabled = False
            result = await compiler.ingest_source(tmp_vault / "raw" / "plain.txt")

        post = fm.load(str(result[0]))
        assert "masking_applied" not in post.metadata
        assert "masking_rules_version" not in post.metadata
