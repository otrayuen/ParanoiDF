'''An endobj inside a string or stream must not end the object.

getIndirectObjects used a non-greedy ".*?endobj" search. A JavaScript string
that contains that word was cut off there, and the dictionary was parsed as
empty, so the rest of the script was discarded while the parse still succeeded.
'''
import os
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


class EndobjInsideObjectTest(unittest.TestCase):
    def test_javascript_containing_endobj_is_kept(self):
        script = "alert('endobj'); this.moreMalware()"
        raw = ('1 0 obj\n<< /JS (%s) >>\nendobj\n' % script).encode('latin-1')
        pdf = _parse(_pdf([(1, raw)]))
        obj = pdf.body[0].getObject(1)
        self.assertEqual(obj.getType(), 'dictionary')
        js = obj.getElementByName('/JS')
        self.assertIsNotNone(js)
        self.assertEqual(js.getValue(), script)
        self.assertEqual(pdf.getErrors(), [])

    def test_nested_and_escaped_parentheses_do_not_hide_the_real_endobj(self):
        script = "call('(endobj)'); keep \\(this\\)"
        raw = ('1 0 obj\n<< /JS (%s) >>\nendobj\n' % script).encode('latin-1')
        pdf = _parse(_pdf([(1, raw)]))
        js = pdf.body[0].getObject(1).getElementByName('/JS')
        self.assertEqual(js.getValue(), "call('(endobj)'); keep (this)")

    def test_commented_endobj_does_not_end_the_object(self):
        raw = b'1 0 obj\n% endobj\n<< /Type /Catalog /Kept /Yes >>\nendobj\n'
        pdf = _parse(_pdf([(1, raw)]))
        obj = pdf.body[0].getObject(1)
        self.assertEqual(obj.getElementByName('/Kept').getValue(), '/Yes')

    def test_stream_text_containing_endobj_keeps_the_following_operators(self):
        stream = b'BT (endobj) Tj ET more-operators\n'
        raw = (
            b'2 0 obj\n<< /Length %d >>\nstream\n' % len(stream)
            + stream
            + b'endstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObjectsIds(), [1, 2])
        # The newline that terminates the stream line is the delimiter before endstream.
        self.assertEqual(
            pdf.body[0].getObject(2).getStream(),
            'BT (endobj) Tj ET more-operators',
        )

    def test_length1_does_not_override_length_when_stream_contains_endobj(self):
        stream = b'endobj!'
        raw = (
            b'2 0 obj\n<</Length1 99999/Length %d>>stream\r\n' % len(stream)
            + stream
            + b'\r\nendstream\r\nendobj\r\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), stream.decode('latin-1'))

    def test_compressed_stream_with_endobj_still_decodes(self):
        decoded = b'page text endobj and the rest of the content'
        compressed = zlib.compress(decoded)
        raw = (
            b'2 0 obj\n<< /Filter /FlateDecode /Length %d >>\nstream\n' % len(compressed)
            + compressed
            + b'\nendstream\nendobj\n'
        )
        pdf = _parse(_pdf([
            (1, b'1 0 obj\n<< /Type /Catalog >>\nendobj\n'),
            (2, raw),
        ]))
        self.assertEqual(pdf.body[0].getObject(2).getStream(), decoded.decode('latin-1'))

    def test_existing_document_objects_stay_intact(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        status, pdf = PDFParser().parse(os.path.join(root, 'docs', 'Functionality.pdf'))
        self.assertEqual(status, 0)
        body = pdf.body[0]
        self.assertEqual(len(body.getObjectsIds()), 244)
        self.assertEqual(pdf.getErrors(), [])
        stream = body.getObject(13)
        # /Length is 12220. The reader also keeps the EOL that sits before endstream.
        self.assertEqual(len(stream.getRawStream()), 12222)
        self.assertEqual(len(stream.getStream()), 24332)


if __name__ == '__main__':
    unittest.main()
