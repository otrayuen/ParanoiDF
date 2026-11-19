'''The cross-reference table is the one startxref points at.

Page text that contains the words "xref" or "trailer" must not be treated as
the table. Splitting at the first match drops every object after that word.
'''

import os
import tempfile
import unittest

from PDFCore import PDFParser


def _pdf_with_body(stream_text):
    '''A one-page PDF whose content stream is stream_text.'''
    objects = []
    objects.append('1 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n' % (
        len(stream_text) + 1, stream_text))
    objects.append('2 0 obj\n<< /Type /Catalog /Pages 3 0 R >>\nendobj\n')
    objects.append('3 0 obj\n<< /Type /Pages /Kids [4 0 R] /Count 1 >>\nendobj\n')
    objects.append(
        '4 0 obj\n<< /Type /Page /Parent 3 0 R /Contents 1 0 R '
        '/MediaBox [0 0 200 200] >>\nendobj\n')
    header = '%PDF-1.4\n'
    body = ''
    offsets = [0]
    cursor = len(header)
    for obj in objects:
        offsets.append(cursor)
        body += obj
        cursor += len(obj)
    xref_offset = cursor
    xref = 'xref\n0 5\n'
    xref += '0000000000 65535 f \n'
    for offset in offsets[1:]:
        xref += '%010d 00000 n \n' % offset
    trailer = 'trailer\n<< /Size 5 /Root 2 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref_offset
    return header + body + xref + trailer


def _object_count(raw):
    handle, path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.write(handle, raw.encode('latin-1'))
        os.close(handle)
        status, pdf = PDFParser().parse(path, forceMode=True)
    finally:
        if os.path.exists(path):
            os.remove(path)
    if status != 0 or pdf is None:
        raise AssertionError('parse failed: %s' % (status,))
    stats = pdf.getStats()
    return stats['Objects'], stats['Errors']


class XrefKeywordInContentTest(unittest.TestCase):
    def test_page_text_does_not_hide_later_objects(self):
        raw = _pdf_with_body('See the xref or trailer before the real table.')
        count, errors = _object_count(raw)
        self.assertEqual(int(count), 4)
        self.assertNotIn('Xref section not found', errors)

    def test_plain_page_still_parses(self):
        raw = _pdf_with_body('Hello')
        count, errors = _object_count(raw)
        self.assertEqual(int(count), 4)
        self.assertNotIn('Xref section not found', errors)


if __name__ == '__main__':
    unittest.main()
