"""Content masking: regex + Presidio NER + LLM-based sensitive content redaction before compilation."""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from openai import AsyncOpenAI
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine

from cortex.compiler.prompts import MASKING_SYSTEM_PROMPT
from cortex.config import settings

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_PATTERNS_HEADER_RE = re.compile(r"^### Patterns\s*$", re.MULTILINE)
_PATTERN_ITEM_RE = re.compile(r"^- `(.+?)`\s*$", re.MULTILINE)


@dataclass
class MaskingRule:
    """A single masking category parsed from the rules file."""
    category: str
    description: str
    patterns: list[str] = field(default_factory=list)


@dataclass
class MaskingRules:
    """All parsed masking rules plus the raw markdown for LLM context."""
    rules: list[MaskingRule]
    raw_markdown: str


@dataclass
class MaskingResult:
    """Outcome of applying content masking."""
    content: str
    applied_rules: int
    llm_masking: bool
    presidio_entities: int = 0


def _parse_rules_markdown(text: str) -> list[MaskingRule]:
    """Parse ## sections from the masking rules markdown file."""
    section_starts = list(_SECTION_RE.finditer(text))
    if not section_starts:
        return []

    rules: list[MaskingRule] = []
    for i, match in enumerate(section_starts):
        category = match.group(1).strip()
        start = match.end()
        end = section_starts[i + 1].start() if i + 1 < len(section_starts) else len(text)
        body = text[start:end]

        patterns_match = _PATTERNS_HEADER_RE.search(body)
        if patterns_match:
            description = body[:patterns_match.start()].strip()
            patterns_block = body[patterns_match.end():]
            patterns = _PATTERN_ITEM_RE.findall(patterns_block)
        else:
            description = body.strip()
            patterns = []

        rules.append(MaskingRule(category=category, description=description, patterns=patterns))

    return rules


_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None


def _get_analyzer() -> AnalyzerEngine:
    """Lazy-initialise the shared Presidio AnalyzerEngine (expensive to construct)."""
    global _analyzer  # noqa: PLW0603
    if _analyzer is None:
        _analyzer = AnalyzerEngine()
    return _analyzer


def _get_anonymizer() -> AnonymizerEngine:
    global _anonymizer  # noqa: PLW0603
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


class ContentMasker:
    """Applies masking rules to extracted content before LLM enrichment."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path
        self._rules_path = vault_path / settings.masking_rules_path

    def load_rules(self) -> MaskingRules | None:
        """Load and parse .cortex/masking-rules.md. Returns None if missing or empty."""
        if not self._rules_path.exists():
            logger.warning("Masking rules file not found: %s", self._rules_path)
            return None

        raw = self._rules_path.read_text()
        parsed = _parse_rules_markdown(raw)
        if not parsed:
            logger.warning("No masking rules found in %s", self._rules_path)
            return None

        return MaskingRules(rules=parsed, raw_markdown=raw)

    def apply_regex_rules(self, content: str, rules: MaskingRules) -> tuple[str, int]:
        """Apply deterministic regex patterns from all rules. Returns (masked_content, match_count)."""
        total_matches = 0
        for rule in rules.rules:
            for pattern in rule.patterns:
                try:
                    compiled = re.compile(pattern)
                    matches = compiled.findall(content)
                    if matches:
                        total_matches += len(matches)
                        content = compiled.sub(f"[{rule.category.upper()}]", content)
                except re.error:
                    logger.warning("Invalid regex pattern in '%s': %s", rule.category, pattern)
        return content, total_matches

    @staticmethod
    def _build_custom_recognizers(rules: MaskingRules) -> list[PatternRecognizer]:
        """Convert masking-rules.md regex patterns into Presidio PatternRecognizers."""
        recognizers: list[PatternRecognizer] = []
        for rule in rules.rules:
            if not rule.patterns:
                continue
            entity_type = rule.category.upper().replace(" ", "_")
            patterns = [
                Pattern(name=f"{entity_type}_{i}", regex=p, score=0.85)
                for i, p in enumerate(rule.patterns)
            ]
            recognizers.append(
                PatternRecognizer(
                    supported_entity=entity_type,
                    patterns=patterns,
                    supported_language="en",
                )
            )
        return recognizers

    def apply_presidio_masking(
        self,
        content: str,
        language: str = "en",
        rules: MaskingRules | None = None,
    ) -> tuple[str, int]:
        """Detect and anonymise PII using Presidio NER + built-in + custom recognizers.

        Returns (masked_content, entity_count).
        """
        analyzer = _get_analyzer()
        anonymizer = _get_anonymizer()

        ad_hoc_recognizers = self._build_custom_recognizers(rules) if rules else None
        results = analyzer.analyze(
            text=content,
            language=language,
            ad_hoc_recognizers=ad_hoc_recognizers,
        )
        if not results:
            return content, 0

        anonymized = anonymizer.anonymize(text=content, analyzer_results=results)
        return anonymized.text, len(results)

    async def apply_llm_masking(self, content: str, rules: MaskingRules) -> str:
        """Send pre-masked content + rules to LLM for context-aware masking."""
        model = settings.masking_model or settings.compiler_model
        api_key = settings.llm_api_key
        if not api_key:
            return content

        client = AsyncOpenAI(api_key=api_key, base_url=settings.llm_base_url)
        try:
            response = await client.chat.completions.create(
                model=model,
                max_tokens=settings.compiler_max_tokens,
                messages=[
                    {"role": "system", "content": MASKING_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"## Masking Rules\n\n{rules.raw_markdown}\n\n"
                            f"## Document to Mask\n\n{content}"
                        ),
                    },
                ],
            )
            return response.choices[0].message.content or content
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("LLM masking failed, returning regex-only result")
            return content

    def rules_version(self) -> str | None:
        """Compute SHA-256 hash of the rules file for frontmatter metadata."""
        if not self._rules_path.exists():
            return None
        content = self._rules_path.read_bytes()
        return f"sha256:{hashlib.sha256(content).hexdigest()}"

    async def mask(self, content: str) -> MaskingResult:
        """Full masking pipeline: regex → Presidio NER → LLM."""
        rules = self.load_rules()
        if rules is None:
            return MaskingResult(content=content, applied_rules=0, llm_masking=False)

        masked, regex_count = self.apply_regex_rules(content, rules)

        masked, presidio_count = self.apply_presidio_masking(masked, rules=rules)

        llm_used = False
        if settings.llm_api_key:
            masked = await self.apply_llm_masking(masked, rules)
            llm_used = True

        return MaskingResult(
            content=masked,
            applied_rules=regex_count,
            llm_masking=llm_used,
            presidio_entities=presidio_count,
        )
