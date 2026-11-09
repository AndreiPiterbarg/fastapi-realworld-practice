"""``EmailStr`` exactly as the API shipped it: pydantic 1.9 on email-validator 1.1.3.

Stored users and the mobile clients depend on 1.9's accepted set and stored
value, which email-validator 2.x changed (special-use domains, Unicode
handling, length limits). pydantic 1.9 only used email-validator to accept or
reject the address (syntax only, no DNS) and stored its own form: an optional
``Name <address>`` wrapper removed, whitespace stripped, the local part kept as
sent and the domain lowercased.
"""
import re
import unicodedata
from typing import Tuple

import idna
from pydantic import AfterValidator, WithJsonSchema
from pydantic_core import PydanticCustomError
from typing_extensions import Annotated

from app.models.common import CoercedStr

EMAIL_MAX_LENGTH = 254
LOCAL_PART_MAX_LENGTH = 64
DOMAIN_MAX_LENGTH = 255

_ATEXT = r"a-zA-Z0-9_!#\$%&'\*\+\-/=\?\^`\{\|\}~"
_ATEXT_UTF8 = "{0}\u0080-\U0010FFFF".format(_ATEXT)
_DOT_ATOM = r"[{0}]+(?:\.[{0}]+)*"
_HOSTNAME_LABEL = r"(?:(?:[a-zA-Z0-9][a-zA-Z0-9\-]*)?[a-zA-Z0-9])"

_ASCII_LOCAL_REGEX = re.compile(_DOT_ATOM.format(_ATEXT))
_UTF8_LOCAL_REGEX = re.compile(_DOT_ATOM.format(_ATEXT_UTF8))
_HOSTNAME_REGEX = re.compile(r"{0}(?:\.{0})*".format(_HOSTNAME_LABEL))
_TLD_REGEX = re.compile(r"[A-Za-z]\Z")
_PRETTY_EMAIL_REGEX = re.compile(r"([\w ]*?) *<(.*)> *")


def _email_error() -> PydanticCustomError:
    return PydanticCustomError(
        "value_error.email",
        "value is not a valid email address",
    )


def _check_local_part(local: str) -> Tuple[str, bool]:
    """Return 1.1.3's normalised local part and whether it is ASCII."""
    if not local or len(local) > LOCAL_PART_MAX_LENGTH:
        raise _email_error()
    if _ASCII_LOCAL_REGEX.fullmatch(local):
        return local, True
    if _UTF8_LOCAL_REGEX.fullmatch(local):
        return unicodedata.normalize("NFC", local), False
    raise _email_error()


def _remap_domain(domain: str) -> str:
    if not domain:
        raise _email_error()
    try:
        domain = idna.uts46_remap(domain, std3_rules=False, transitional=False)
    except idna.IDNAError:
        raise _email_error()
    if domain.startswith(".") or domain.endswith(".") or ".." in domain:
        raise _email_error()
    return domain


def _is_hostname(ascii_domain: str) -> bool:
    checks = (
        len(ascii_domain) <= DOMAIN_MAX_LENGTH,
        _HOSTNAME_REGEX.fullmatch(ascii_domain),
        "." in ascii_domain,
        _TLD_REGEX.search(ascii_domain),
    )
    return all(checks)


def _check_domain_part(domain: str) -> Tuple[str, str]:
    """Return 1.1.3's ASCII and Unicode forms of the domain."""
    domain = _remap_domain(domain)
    try:
        ascii_domain = idna.encode(domain, uts46=False).decode("ascii")
    except idna.IDNAError:
        raise _email_error()
    try:
        unicode_domain = idna.decode(ascii_domain.encode("ascii"))
    except idna.IDNAError:
        raise _email_error()
    if not _is_hostname(ascii_domain):
        raise _email_error()
    return ascii_domain, unicode_domain


def _check_syntax(email: str) -> None:
    """email-validator 1.1.3's ``validate_email(check_deliverability=False)``."""
    if email.count("@") != 1:
        raise _email_error()
    local, domain = email.split("@")
    local, is_ascii = _check_local_part(local)
    ascii_domain, domain = _check_domain_part(domain)
    if is_ascii and len("{0}@{1}".format(local, ascii_domain)) > EMAIL_MAX_LENGTH:
        raise _email_error()
    if len("{0}@{1}".format(local, domain).encode("utf8")) > EMAIL_MAX_LENGTH:
        raise _email_error()


def validate_email(email: str) -> str:
    """pydantic 1.9's ``EmailStr.validate``."""
    match = _PRETTY_EMAIL_REGEX.fullmatch(email)
    if match:
        email = match.group(2)
    email = email.strip()
    _check_syntax(email)
    at_index = email.index("@")
    return email[:at_index] + email[at_index:].lower()


Email = Annotated[
    CoercedStr,
    AfterValidator(validate_email),
    WithJsonSchema({"type": "string", "format": "email"}),
]
