'''Object streams whose /Length is an indirect reference must still expand.

PDFObjectStream.resolveReferences used the offset digits as a string slice and
called readObject on the class, so a FlateDecode object stream with
"/Length N 0 R" raised TypeError and aborted the parse. Every object stored
in that stream was dropped with it.
'''

import os
import tempfile
import unittest
import zlib

from PDFCore import PDFParser


def _object_stream_pdf(indirect_length):
    '''A catalog plus one compressed object, with /Length direct or indirect.'''
    decoded = b'6 0 << /Foo /Bar >>'
    compressed = zlib.compress(decoded)
    length = len(compressed)
    if indirect_length:
        stream_dict = (
            b'4 0 obj\n<< /Type /ObjStm /N 1 /First 4 '
            b'/Filter /FlateDecode /Length 5 0 R >>\nstream\n'
        )
    else:
        stream_dict = (
            '4 0 obj\n<< /Type /ObjStm /N 1 /First 4 '
            '/Filter /FlateDecode /Length %d >>\nstream\n' % length
        ).encode('latin-1')
    objects = [
        (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
        (4, stream_dict + compressed + b'\nendstream\nendobj\n'),
        (5, ('5 0 obj\n%d\nendobj\n' % length).encode('latin-1')),
    ]
    header = b'%PDF-1.5\n%\x80\x81\x82\x83\n'
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

    xref = b'xref\n0 2\n' + entry(0, 65535, 'f') + entry(offsets[1], 0, 'n')
    xref += b'4 2\n' + entry(offsets[4], 0, 'n') + entry(offsets[5], 0, 'n')
    trailer = (
        'trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref_offset
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


class ObjectStreamIndirectLengthTest(unittest.TestCase):
    def test_indirect_length_expands_compressed_object(self):
        pdf = _parse(_object_stream_pdf(indirect_length=True))
        body = pdf.body[0]
        self.assertEqual(body.getObjectsIds(), [6, 1, 4, 5])
        self.assertEqual(body.getCompressedObjects(), [6])
        compressed = body.getObject(6)
        self.assertIsNotNone(compressed)
        self.assertIn('/Foo', compressed.getValue())
        stream = body.getObject(4)
        self.assertNotIn('Missing offsets in object stream', stream.getErrors())

    def test_direct_length_still_expands_compressed_object(self):
        pdf = _parse(_object_stream_pdf(indirect_length=False))
        body = pdf.body[0]
        self.assertEqual(body.getObjectsIds(), [6, 1, 4, 5])
        self.assertEqual(body.getCompressedObjects(), [6])
        self.assertIn('/Foo', body.getObject(6).getValue())


if __name__ == '__main__':
    unittest.main()
