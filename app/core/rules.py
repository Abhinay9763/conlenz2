from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{4}\b")
IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PRIVATE) KEY-----")
API_KEY_RE = re.compile(
    r"\b(api[_-]?key|access[_-]?key|secret[_-]?key|token)\b[^\n\r]{0,50}([A-Za-z0-9_\-]{16,})",
    re.IGNORECASE,
)


@dataclass
class Finding:
    file_path: str
    rule: str
    severity: str
    confidence: str
    snippet: str
    location: str


def apply_rules(
    *,
    text: str,
    file_path: str,
    allowed_domains: set[str],
    allowed_emails: set[str],
    flags: dict[str, bool],
    personal_names: list[str],
) -> list[Finding]:
    findings: list[Finding] = []
    if not text:
        return findings

    if flags.get("private_key", True):
        for match in PRIVATE_KEY_RE.finditer(text):
            findings.append(_mk_finding(file_path, "Private Key", "high", "high", match.group(0), text, match.start()))

    if flags.get("api_key", True):
        for match in API_KEY_RE.finditer(text):
            findings.append(_mk_finding(file_path, "API Key", "high", "medium", match.group(0), text, match.start()))

    if flags.get("email", True):
        for match in EMAIL_RE.finditer(text):
            email = match.group(0)
            if _email_allowed(email, allowed_domains, allowed_emails):
                continue
            findings.append(_mk_finding(file_path, "Email", "medium", "high", email, text, match.start()))

    if flags.get("phone", True):
        for match in PHONE_RE.finditer(text):
            value = match.group(0)
            if len(re.sub(r"\D", "", value)) < 9:
                continue
            findings.append(_mk_finding(file_path, "Phone", "medium", "medium", value, text, match.start()))

    if flags.get("ip_address", True):
        for match in IPV4_RE.finditer(text):
            value = match.group(0)
            if _is_private_ip(value):
                continue
            findings.append(_mk_finding(file_path, "IP Address", "low", "medium", value, text, match.start()))

    if flags.get("credit_card", True):
        for match in CARD_RE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if not (13 <= len(digits) <= 19):
                continue
            if not _luhn_valid(digits):
                continue
            findings.append(_mk_finding(file_path, "Credit Card", "high", "high", match.group(0), text, match.start()))

    if flags.get("aadhaar", True):
        for match in AADHAAR_RE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) != 12:
                continue
            confidence = "high" if _verhoeff_valid(digits) else "medium"
            severity = "high" if _has_keyword_near(text, match.start(), ["aadhaar", "uidai"]) else "medium"
            findings.append(_mk_finding(file_path, "Aadhaar", severity, confidence, match.group(0), text, match.start()))

    if flags.get("pan", True):
        for match in PAN_RE.finditer(text):
            severity = "medium"
            confidence = "medium"
            if _has_keyword_near(text, match.start(), ["pan", "income tax"]):
                confidence = "high"
                severity = "high"
            findings.append(_mk_finding(file_path, "PAN", severity, confidence, match.group(0), text, match.start()))

    if flags.get("personal_name", True) and personal_names:
        for name in personal_names:
            clean = name.strip()
            if not clean:
                continue
            pattern = re.compile(rf"\b{re.escape(clean)}\b", re.IGNORECASE)
            for match in pattern.finditer(text):
                findings.append(_mk_finding(file_path, "Personal Name", "low", "low", clean, text, match.start()))

    return findings


def _mk_finding(
    file_path: str,
    rule: str,
    severity: str,
    confidence: str,
    snippet: str,
    text: str | None = None,
    match_index: int | None = None,
) -> Finding:
    location = ""
    if text is not None and match_index is not None:
        location = f"line {_line_number(match_index, text)}"
    return Finding(
        file_path=file_path,
        rule=rule,
        severity=severity,
        confidence=confidence,
        snippet=_truncate(snippet, 180),
        location=location,
    )


def _line_number(index: int, text: str) -> int:
    return max(1, text.count("\n", 0, index) + 1)


def _truncate(value: str, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _email_allowed(email: str, allowed_domains: set[str], allowed_emails: set[str]) -> bool:
    normalized = email.strip().lower()
    domain = normalized.split("@", 1)[1] if "@" in normalized else ""
    if normalized in allowed_emails:
        return True
    if domain and domain in allowed_domains:
        return True
    return False


def _is_private_ip(ip_value: str) -> bool:
    parts = ip_value.split(".")
    try:
        numbers = [int(part) for part in parts]
    except ValueError:
        return False
    if len(numbers) != 4:
        return False
    if numbers[0] == 10:
        return True
    if numbers[0] == 172 and 16 <= numbers[1] <= 31:
        return True
    if numbers[0] == 192 and numbers[1] == 168:
        return True
    if numbers[0] == 127:
        return True
    return False


def _luhn_valid(number: str) -> bool:
    total = 0
    reverse_digits = number[::-1]
    for index, char in enumerate(reverse_digits):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _verhoeff_valid(number: str) -> bool:
    d_table = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    p_table = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]

    c = 0
    reversed_digits = list(reversed([int(x) for x in number]))
    for i, item in enumerate(reversed_digits):
        c = d_table[c][p_table[i % 8][item]]
    return c == 0


def _has_keyword_near(text: str, index: int, keywords: list[str], window: int = 50) -> bool:
    start = max(0, index - window)
    end = min(len(text), index + window)
    scope = text[start:end].lower()
    return any(keyword in scope for keyword in keywords)
