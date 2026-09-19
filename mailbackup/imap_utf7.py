from __future__ import annotations

import base64


def decode(value: str) -> str:
    """Decode IMAP modified UTF-7 folder names (RFC 3501)."""
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != '&':
            output.append(value[index])
            index += 1
            continue
        end = value.find('-', index)
        if end < 0:
            output.append(value[index:])
            break
        encoded = value[index + 1:end]
        if not encoded:
            output.append('&')
        else:
            padded = encoded.replace(',', '/') + '=' * ((4 - len(encoded) % 4) % 4)
            try:
                output.append(base64.b64decode(padded).decode('utf-16-be'))
            except (ValueError, UnicodeError):
                output.append(value[index:end + 1])
        index = end + 1
    return ''.join(output)

