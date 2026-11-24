'''PNG predictors must unfilter every byte of the row.

post_prediction walked /Columns + 1 bytes. /Columns is a sample count, so a
1-bit or 4-bit Sub/Up/Paeth row raised IndexError and the parser exited
before any later object. An RGB row was only partly reconstructed, so the
decoded stream was wrong.
'''
import os
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PDFCore import PDFParser
from PDFFilters import post_prediction


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


def _ords(text):
    return [ord(char) for char in text]


class PngPredictorRowWidthTest(unittest.TestCase):
    def test_gray_sub_row_is_unchanged(self):
        # 8-bit gray, columns equals the data-byte count. Filter Sub.
        # raw 10, 20, 40 encodes as 10, 10, 20.
        decoded = post_prediction(bytes([1, 10, 10, 20]).decode('latin-1'), 15, 3, 1, 8)
        self.assertEqual(decoded[0], 0)
        self.assertEqual(_ords(decoded[1]), [10, 20, 40])

    def test_one_bit_sub_row_does_not_crash(self):
        # 16 samples at 1 bit are 2 bytes. The old loop ran to columns+1.
        decoded = post_prediction(bytes([1, 0xA5, 0x5A]).decode('latin-1'), 15, 16, 1, 1)
        self.assertEqual(decoded[0], 0)
        self.assertEqual(_ords(decoded[1]), [0xA5, 0xFF])

    def test_rgb_up_second_row_is_fully_reconstructed(self):
        # One RGB pixel per row. Up on the second row must add every channel.
        rows = bytes([
            2, 10, 20, 30,
            2, 1, 2, 3,
        ])
        decoded = post_prediction(rows.decode('latin-1'), 15, 1, 3, 8)
        self.assertEqual(decoded[0], 0)
        self.assertEqual(_ords(decoded[1]), [10, 20, 30, 11, 22, 33])

    def test_rgb_sub_row_reconstructs_every_channel(self):
        # Two RGB pixels. Sub stride is 3 bytes, not one sample column.
        # raw 10,20,30,40,50,60 encodes as 10,20,30,30,30,30.
        decoded = post_prediction(
            bytes([1, 10, 20, 30, 30, 30, 30]).decode('latin-1'), 15, 2, 3, 8)
        self.assertEqual(decoded[0], 0)
        self.assertEqual(_ords(decoded[1]), [10, 20, 30, 40, 50, 60])

    def test_parser_keeps_objects_after_one_bit_image(self):
        samples = bytes([1, 0xA5, 0x5A])
        compressed = zlib.compress(samples)
        self.assertNotIn(b'endstream', compressed)
        image = (
            b'4 0 obj\n<< /Type /XObject /Subtype /Image /Width 16 /Height 1 '
            b'/ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /FlateDecode '
            b'/DecodeParms << /Predictor 15 /Colors 1 /BitsPerComponent 1 /Columns 16 >> '
            b'/Length %d >>\nstream\n' % len(compressed)
            + compressed
            + b'\nendstream\nendobj\n'
        )
        raw = _pdf([
            (1, b'1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'),
            (2, b'2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n'),
            (3, b'3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 10 10] >>\nendobj\n'),
            (4, image),
            (5, b'5 0 obj\n<< /KeepMe (AFTER-IMAGE) >>\nendobj\n'),
        ])
        pdf = _parse(raw)
        image_object = pdf.getObject(4)
        self.assertIsNotNone(image_object)
        self.assertEqual(_ords(image_object.getStream()), [0xA5, 0xFF])
        later = pdf.getObject(5)
        self.assertIsNotNone(later)
        self.assertIn('AFTER-IMAGE', later.getValue())


if __name__ == '__main__':
    unittest.main()
