"""Guardrails applied before any planner or specialist runs, and to every answer.

Deterministic checks here run in both demo and live mode, so they never depend
on a model. In live mode, Amazon Bedrock Guardrails adds a managed layer on
the planner call (see BedrockQuestionPlanner). The app reads and explains
records; it never changes them, and it never reveals personal data about people.
"""

import re
from dataclasses import dataclass

SCOPE_HELP = (
    "I answer questions about this business unit's orders, shipments, invoices, receipts, "
    'order holds, and customer balances. Try: "Which shipments are unbilled?", '
    '"Show overdue invoices", or "Summarize DEMO-CUST-000001".'
)

_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email address": re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"),
    "US Social Security number": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone number": re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\w)"),
    "IBAN": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
}
_CARD_CANDIDATE = re.compile(r"(?<!\w)(?:\d[ -]?){13,19}(?!\w)")

_PII_REQUEST = re.compile(
    r"\b(ssn|social security|credit card number|card number|bank account|account number|routing number|"
    r"date of birth|dob|passport|driver'?s? licen[cs]e|home address|street address|personal address|"
    r"password|api key|salary|tax id|phone number|email address|personal email|personal phone)\b",
    re.IGNORECASE,
)

_ACTION_REQUEST = re.compile(
    r"\b(approve|delete|refund|cancel the|release (the )?hold|mark\b.*\bpaid|"
    r"post (the |a )?payment|send (an |a |the )?(email|message|reminder)|write off|"
    r"ignore (all |previous |the |your )?(rules|instructions|guidelines)|system prompt|reveal your)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardrailVerdict:
    code: str
    message: str


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _contains_card_number(text: str) -> bool:
    for match in _CARD_CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return True
    return False


def check_question(question: str) -> GuardrailVerdict | None:
    """Returns a refusal when the question must not reach a model or specialist,
    or None when it may proceed. Order matters: identifiers in the text are
    reported first, because they are the most specific reason to stop.
    """
    for label, pattern in _PII_PATTERNS.items():
        if pattern.search(question):
            return GuardrailVerdict(
                code="guardrail_pii_in_question",
                message=(
                    f"Your question contains a {label}. Please remove personal details and ask again. "
                    "Refer to records by their IDs instead, such as an invoice or customer ID."
                ),
            )
    if _contains_card_number(question):
        return GuardrailVerdict(
            code="guardrail_pii_in_question",
            message="Your question contains what looks like a card number. Please remove it and ask again.",
        )
    if _PII_REQUEST.search(question):
        return GuardrailVerdict(
            code="guardrail_pii_request",
            message=(
                "I can't provide personal information about people, such as identifiers, bank or card "
                "details, contact details, or addresses. I can explain balances, invoice and order status, "
                "and holds by record ID."
            ),
        )
    if _ACTION_REQUEST.search(question):
        return GuardrailVerdict(
            code="guardrail_action_request",
            message=(
                "I can only read and explain records. I can't change, approve, pay, release, or send "
                "anything. "
                "To follow up on an item, create a task in Tasks."
            ),
        )
    return None


_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_PII_PATTERNS["email address"], "[email removed]"),
    (_PII_PATTERNS["US Social Security number"], "[SSN removed]"),
    (_PII_PATTERNS["phone number"], "[phone removed]"),
)


def redact_output(text: str) -> str:
    """Last line of defense on answers: removes contact details and SSNs that
    might appear in a stored record or document excerpt.
    """
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text
