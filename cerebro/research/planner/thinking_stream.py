"""Utilities for extracting live thinking text from streamed JSON output."""

from __future__ import annotations


class ThinkingStreamExtractor:
    """Incrementally extracts only the thinking field from streamed JSON text."""

    def __init__(self) -> None:
        self._buffer = ""
        self._started = False
        self._done = False
        self._scan_pos = 0
        self._escape = False
        self._unicode_mode = False
        self._unicode_digits = ""
        self.emitted_chars = 0

    def feed(self, chunk: str) -> str:
        """Consume a streamed chunk and return newly decoded thinking text."""
        if self._done:
            return ""

        self._buffer += chunk

        if not self._started:
            start = self._find_thinking_start()
            if start is None:
                return ""
            self._started = True
            self._scan_pos = start

        out: list[str] = []
        while self._scan_pos < len(self._buffer):
            ch = self._buffer[self._scan_pos]
            self._scan_pos += 1

            if self._unicode_mode:
                if ch.lower() in "0123456789abcdef":
                    self._unicode_digits += ch
                    if len(self._unicode_digits) == 4:
                        out.append(chr(int(self._unicode_digits, 16)))
                        self._unicode_digits = ""
                        self._unicode_mode = False
                        self._escape = False
                else:
                    # Invalid unicode escape sequence; fail open by emitting raw tail.
                    out.append("\\u" + self._unicode_digits + ch)
                    self._unicode_digits = ""
                    self._unicode_mode = False
                    self._escape = False
                continue

            if self._escape:
                mapping = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if ch == "u":
                    self._unicode_mode = True
                    self._unicode_digits = ""
                    continue
                out.append(mapping.get(ch, ch))
                self._escape = False
                continue

            if ch == "\\":
                self._escape = True
                continue

            if ch == '"':
                self._done = True
                break

            out.append(ch)

        delta = "".join(out)
        self.emitted_chars += len(delta)
        return delta

    def _find_thinking_start(self) -> int | None:
        key_idx = self._buffer.find('"thinking"')
        if key_idx == -1:
            return None

        colon_idx = self._buffer.find(":", key_idx + len('"thinking"'))
        if colon_idx == -1:
            return None

        idx = colon_idx + 1
        while idx < len(self._buffer) and self._buffer[idx] in " \t\r\n":
            idx += 1

        if idx >= len(self._buffer):
            return None

        if self._buffer[idx] != '"':
            # Unexpected non-string; mark done so we avoid endless scans.
            self._done = True
            return None

        return idx + 1
