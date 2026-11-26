'''Literal-string octal escapes must be decoded in one left-to-right pass.

PDFString.update collapsed \\\\ to a single backslash and then replaced every
octal escape globally. A literal backslash followed by digits became the octal
character, and a short escape rewrote the prefix of a later escape. Wrapped
strings that continued with a backslash before the line break kept both.
'''
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PDFCore import PDFParser


def _pdf(objects, root=1):
    header = b'%PDF-1.4\n%\x80\x81\x82\x83\n'
    body = b''
    offsets = {}
    cursor = len(header)
    for obj_id, raw in objects:
        offsets[obj_id] = cursor
        body += raw
        cursor += len(raw)
    xref_offset = cursor

    def entry(offset, generation, kind):
        return ('%010d %05d %s \n' % (offset, generation, kind)).encode('latin-1')

    max_id = max(offsets)
    xref = b'xref\n0 %d\n' % (max_id + 1)
    xref += entry(0, 65535, 'f')
    for obj_id in range(1, max_id + 1):
        if obj_id in offsets:
            xref += entry(offsets[obj_id], 0, 'n')
        else:
            xref += entry(0, 65535, 'f')
    trailer = (
        'trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n'
        % (max_id + 1, root, xref_offset)
    ).encode('latin-1')
    return header + body + xref + trailer


def _parse(raw):
    handle, path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.write(handle, raw)
        os.close(handle)
        status, pdf = PDFParser().parse(path)
    finally:
        if os.path.exists(path):
            os.remove(path)
    if status != 0 or pdf is None:
        raise AssertionError('parse failed: %s' % (status,))
    return pdf


class LiteralOctalEscapeTest(unittest.TestCase):
    def test_escaped_backslash_before_digits_stays_a_backslash(self):
        # (re = /\\1/) is the characters re = /\1/ . The old decoder treated
        # the remaining backslash as an octal escape and stored a control byte.
        raw = _pdf([
            (1, b'1 0 obj\n<< /JS (re = /\\\\1/) /Next (ok) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/JS').getValue(), 're = /\\1/')
        self.assertEqual(obj.getElement('/Next').getValue(), 'ok')
        self.assertEqual(obj.getErrors(), [])

    def test_short_octal_does_not_rewrite_a_later_escape(self):
        # (\10\101) is byte 8 then 'A'. Replacing every \10 also consumed the
        # first two digits of \101 and left the last digit behind.
        raw = _pdf([
            (1, b'1 0 obj\n<< /Data (\\10\\101) /Next (ok) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/Data').getValue(), '\x08A')
        self.assertEqual(obj.getElement('/Next').getValue(), 'ok')

    def test_three_digit_octal_and_known_escapes_still_decode(self):
        raw = _pdf([
            (1, b'1 0 obj\n<< /Oct (\\101\\102) /NL (a\\nb) /Esc (see 1\\)) /Path (C:\\\\Windows\\\\) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/Oct').getValue(), 'AB')
        self.assertEqual(obj.getElement('/NL').getValue(), 'a\nb')
        self.assertEqual(obj.getElement('/Esc').getValue(), 'see 1)')
        self.assertEqual(obj.getElement('/Path').getValue(), 'C:\\Windows\\')

    def test_backslash_before_line_break_is_a_continuation(self):
        # (hel\<newline>lo) is "hello". The break and the backslash are not data.
        raw = _pdf([
            (1, b'1 0 obj\n<< /Data (hel\\\nlo) /CR (hel\\\rlo) /CRLF (hel\\\r\nlo) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/Data').getValue(), 'hello')
        self.assertEqual(obj.getElement('/CR').getValue(), 'hello')
        self.assertEqual(obj.getElement('/CRLF').getValue(), 'hello')


if __name__ == '__main__':
    unittest.main()
