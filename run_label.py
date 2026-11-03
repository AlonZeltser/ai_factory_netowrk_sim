"""Turn a run label into a short, filesystem-safe name.

Run labels look like "<config path> | key=value | key=value". Used whole as a file or folder
name, a long or absolute config path can exceed the 255-character limit for one path
component (Windows fails with WinError 123).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import PurePath

# Longest file/folder-name fragment produced here; leaves room for prefixes, suffixes and
# timestamps within the 255-character component limit.
MAX_LABEL_SLUG_LEN = 150
_HASH_LEN = 8


def _slugify(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")


def label_slug(label: str) -> str:
    """Return a filesystem-safe name for `label`, at most MAX_LABEL_SLUG_LEN characters.

    Short labels keep their full slug (the historical naming). Longer ones keep the config
    file name plus the sweep values, shortened if needed, and end with a hash of the full
    label so different runs never share a name.
    """
    full = _slugify(label)
    if full and len(full) <= MAX_LABEL_SLUG_LEN:
        return full

    config_part, *value_parts = [part.strip() for part in label.split("|")]
    readable = _slugify("_".join([PurePath(config_part.replace("\\", "/")).name, *value_parts]))
    digest = hashlib.sha1(label.encode("utf-8")).hexdigest()[:_HASH_LEN]
    keep = MAX_LABEL_SLUG_LEN - _HASH_LEN - 1
    return f"{readable[:keep].rstrip('._')}_{digest}" if readable else digest
