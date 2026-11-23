'''An endstream inside stream data must not end the stream.

readObject stopped at the first "endstream" bytes and ignored /Length. Page
text or JavaScript after that word was dropped, and a Flate stream whose
compressed bytes contained the word decoded to nothing.
'''
import os
import struct
import sys
import tempfile
import unittest
import zlib

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


def _stored_zlib(data):
    '''A zlib wrapper around a stored deflate block, so data bytes stay visible.'''
    block = b'\x01' + struct.pack('<HH', len(data), len(data) ^ 0xFFFF) + data
    a = 1
    b = 0
    for byte in data:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return b'\x78\x01' + block + struct.pack('>I', (b << 16) | a)


class EndstreamInsideStreamTest(unittest.TestCase):
    def test_text_after_endstream_is_kept(self):
        stream = b'Hello endstream world TAIL'
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), stream.decode('latin-1'))
        self.assertEqual(pdf.getErrors(), [])

    def test_javascript_after_endstream_is_kept(self):
        stream = b"app.alert('endstream'); this.exfiltrate()"
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), stream.decode('latin-1'))

    def test_flate_stream_containing_endstream_still_decodes(self):
        decoded = b'page text before endstream and the rest of the payload'
        compressed = _stored_zlib(decoded)
        self.assertIn(b'endstream', compressed)
        self.assertEqual(zlib.decompress(compressed), decoded)
        raw = (
            b'2 0 obj\n<< /Filter /FlateDecode /Length %d >>\nstream\n' % len(compressed)
            + compressed
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        obj = pdf.body[0].getObject(2)
        self.assertEqual(obj.getRawStream(), compressed.decode('latin-1'))
        self.assertEqual(obj.getStream(), decoded.decode('latin-1'))
        self.assertEqual(pdf.getErrors(), [])

    def test_length_in_a_string_does_not_shrink_the_real_stream(self):
        stream = b'endstream stays in the stream'
        raw = (
            b'2 0 obj\n<< /Title (see /Length 1) /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), stream.decode('latin-1'))

    def test_length1_does_not_override_length(self):
        stream = b'endstream!'
        raw = (
            b'2 0 obj\n<</Length1 1/Length %d>>stream\r\n' % len(stream)
            + stream
            + b'\r\nendstream\r\nendobj\r\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), stream.decode('latin-1'))

    def test_stream_without_the_keyword_keeps_the_delimiter_newline(self):
        stream = b'Hello world TAIL'
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        obj = pdf.body[0].getObject(2)
        self.assertEqual(obj.getStream(), stream.decode('latin-1'))
        self.assertEqual(obj.getRawStream(), (stream + b'\n').decode('latin-1'))

    def test_existing_document_objects_stay_intact(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status, pdf = PDFParser().parse(os.path.join(root, 'docs', 'Functionality.pdf'))
        self.assertEqual(status, 0)
        body = pdf.body[0]
        self.assertEqual(len(body.getObjectsIds()), 244)
        self.assertEqual(pdf.getErrors(), [])
        stream = body.getObject(13)
        self.assertEqual(len(stream.getRawStream()), 12222)
        self.assertEqual(len(stream.getStream()), 24332)


if __name__ == '__main__':
    unittest.main()
