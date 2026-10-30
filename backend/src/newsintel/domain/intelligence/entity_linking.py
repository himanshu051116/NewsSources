from __future__ import annotations

import re

ENTITY_EXTERNAL_LINK_VERSION = "entity-external-identifier-v1"


def normalize_external_identifier(namespace: str, external_id: str) -> tuple[str, str]:
    ns = "_".join(namespace.strip().casefold().replace("-", "_").split())
    value = external_id.strip()
    if not ns:
        raise ValueError("external identifier namespace must not be empty")
    if not value:
        raise ValueError("external identifier must not be empty")
    if len(ns) > 80 or len(value) > 300:
        raise ValueError("external identifier exceeds allowed length")
    if ns == "wikidata":
        value = value.upper()
        if not re.fullmatch(r"Q[1-9][0-9]*", value):
            raise ValueError("wikidata identifiers must use Q followed by digits")
    elif ns == "geonames":
        if not value.isdigit():
            raise ValueError("geonames identifiers must be numeric")
    elif ns == "orcid":
        value = value.upper()
        if not re.fullmatch(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", value):
            raise ValueError("invalid ORCID identifier shape")
    elif ns == "lei":
        value = value.upper()
        if not re.fullmatch(r"[A-Z0-9]{20}", value):
            raise ValueError("LEI identifiers must be 20 alphanumeric characters")
    elif ns == "isin":
        value = value.upper()
        if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
            raise ValueError("invalid ISIN identifier shape")
    else:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,299}", value):
            raise ValueError("external identifier contains unsupported characters")
    return ns, value
