'''A %%EOF inside a string or stream must not end the file.

PDFParser.parse split the file at the first %%EOF bytes. An uncompressed
stream (or a string that puts that marker on its own line) made the first
part look trailer-less, and the parser exited before the real catalog.
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


class EofInsideStreamTest(unittest.TestCase):
    def test_stream_text_containing_eof_keeps_the_catalog(self):
        stream = b'hello %%EOF world\n'
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'endstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (2, raw),
            (1, b'1 0 obj\n<< /Type /Catalog /Kept /Yes >>\nendobj\n'),
        ]))
        self.assertEqual(pdf.getUpdates(), 0)
        self.assertEqual(pdf.body[0].getObjectsIds(), [2, 1])
        self.assertEqual(
            pdf.body[0].getObject(1).getElementByName('/Kept').getValue(),
            '/Yes',
        )
        self.assertEqual(pdf.body[0].getObject(2).getStream(), 'hello %%EOF world')
        self.assertEqual(pdf.getErrors(), [])

    def test_eof_line_inside_stream_is_not_an_update(self):
        stream = b'embedded file\n%%EOF\nmore bytes\n'
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'endstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (2, raw),
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
        ]))
        self.assertEqual(pdf.getUpdates(), 0)
        self.assertEqual(pdf.body[0].getObjectsIds(), [2, 1])
        self.assertIn('%%EOF', pdf.body[0].getObject(2).getStream())

    def test_indirect_length_stream_still_skips_an_eof_line(self):
        stream = b'%%EOF\n'
        raw = (
            b'2 0 obj\n<< /Length 4 0 R >>\nstream\n'
            + stream
            + b'endstream\nendobj\n'
            + b'4 0 obj\n%d\nendobj\n' % len(stream)
        )
        pdf = _parse(_pdf([
            (2, raw),
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
        ], root=1))
        self.assertEqual(pdf.getUpdates(), 0)
        self.assertIn(1, pdf.body[0].getObjectsIds())
        self.assertIn(2, pdf.body[0].getObjectsIds())

    def test_string_with_eof_on_its_own_line_keeps_the_next_object(self):
        script = 'line one\n%%EOF\nstill the script'
        raw = ('1 0 obj\n<< /JS (%s) >>\nendobj\n' % script).encode('latin-1')
        pdf = _parse(_pdf([
            (1, raw),
            (2, b'2 0 obj\n<< /Type /Catalog /Kept /Yes >>\nendobj\n'),
        ], root=2))
        self.assertEqual(pdf.getUpdates(), 0)
        js = pdf.body[0].getObject(1).getElementByName('/JS')
        self.assertEqual(js.getValue(), script)
        self.assertEqual(
            pdf.body[0].getObject(2).getElementByName('/Kept').getValue(),
            '/Yes',
        )

    def test_real_incremental_update_still_splits(self):
        first = _pdf([(1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n')])
        second_header_offset = len(first)
        second_obj = b'2 0 obj\n<< /Type /Catalog /Updated true >>\nendobj\n'
        xref_offset = second_header_offset + len(second_obj)
        second = second_obj + (
            'xref\n0 1\n0000000000 65535 f \n'
            'trailer\n<< /Size 3 /Root 2 0 R /Prev 0 >>\nstartxref\n%d\n%%%%EOF\n'
            % xref_offset
        ).encode('latin-1')
        pdf = _parse(first + second)
        self.assertEqual(pdf.getUpdates(), 1)
        self.assertEqual(
            pdf.body[1].getObject(2).getElementByName('/Updated').getValue(),
            'true',
        )

    def test_final_eof_without_a_newline_still_parses(self):
        raw = _pdf([(1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n')])
        self.assertTrue(raw.endswith(b'%%EOF\n'))
        pdf = _parse(raw[:-1])
        self.assertEqual(pdf.getUpdates(), 0)
        self.assertEqual(pdf.body[0].getObjectsIds(), [1])
        self.assertEqual(pdf.getErrors(), [])

    def test_existing_document_is_one_update(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status, pdf = PDFParser().parse(os.path.join(root, 'docs', 'Functionality.pdf'))
        self.assertEqual(status, 0)
        self.assertEqual(pdf.getUpdates(), 0)
        self.assertEqual(len(pdf.body[0].getObjectsIds()), 244)
        self.assertEqual(pdf.getErrors(), [])


if __name__ == '__main__':
    unittest.main()
