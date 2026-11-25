'''Literal strings must count backslashes before a parenthesis.

readUntilClosingDelim treated any parenthesis after a backslash as escaped.
\\\\) is a literal backslash and then the end of the string, and \\\\( starts a
nested string. A directory path that ends in a backslash swallowed every later
key in the same dictionary, and a backslash before a nested parenthesis made
the parser exit before the rest of the file.
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


class LiteralStringBackslashTest(unittest.TestCase):
    def test_directory_path_keeps_the_following_key(self):
        # (C:\\Windows\\) is the path C:\Windows\ and must not absorb /Desc.
        raw = _pdf([
            (1, b'1 0 obj\n<< /F (C:\\\\Windows\\\\) /Desc (next) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/F').getValue(), 'C:\\Windows\\')
        self.assertEqual(obj.getElement('/Desc').getValue(), 'next')
        self.assertEqual(obj.getErrors(), [])

    def test_literal_backslash_before_nested_parenthesis(self):
        # (a\\(b)c) is a\(b)c. The old scan closed at the inner parenthesis
        # and then aborted on the leftover "c)".
        raw = _pdf([
            (1, b'1 0 obj\n<< /F (a\\\\(b)c) /Desc (next) >>\nendobj\n'),
            (2, b'2 0 obj\n<< /KeepMe (AFTER) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/F').getValue(), 'a\\(b)c')
        self.assertEqual(obj.getElement('/Desc').getValue(), 'next')
        later = pdf.getObject(2)
        self.assertIn('AFTER', later.getValue())

    def test_escaped_parenthesis_and_balanced_nesting_still_work(self):
        raw = _pdf([
            (1, b'1 0 obj\n<< /Esc (see 1\\)) /Nest (a(b)c) /Plain (hello) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        obj = pdf.getObject(1)
        self.assertEqual(obj.getElement('/Esc').getValue(), 'see 1)')
        self.assertEqual(obj.getElement('/Nest').getValue(), 'a(b)c')
        self.assertEqual(obj.getElement('/Plain').getValue(), 'hello')
        self.assertEqual(obj.getErrors(), [])


if __name__ == '__main__':
    unittest.main()
