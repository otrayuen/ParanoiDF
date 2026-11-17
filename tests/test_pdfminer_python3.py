'''pdfminer still treated parser strings as bytes.

ToUnicode CMaps, Identity-H text, ASCII85 streams, and standard
encryption all aborted pdf2txt with TypeError on Python 3.
'''
import os
import unittest
from io import StringIO

import py3compat
from pdfminer.ascii85 import ascii85decode
from pdfminer.cmapdb import CMapParser, FileUnicodeMap, IdentityCMap
from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
from pdfminer.pdfparser import PDFParser
from pdfminer.utils import decode_text, nunpack


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pdf(body_objects, trailer):
    chunks = [b'%PDF-1.4\n']
    body = bytearray(chunks[0])
    offsets = {}
    for number, payload in body_objects:
        offsets[number] = len(body)
        body += ('%d 0 obj\n' % number).encode('ascii') + payload + b'\nendobj\n'
    xref = len(body)
    size = max(offsets) + 1
    body += ('xref\n0 %d\n' % size).encode('ascii')
    body += b'0000000000 65535 f \n'
    for number in range(1, size):
        body += ('%010d 00000 n \n' % offsets[number]).encode('ascii')
    body += b'trailer\n' + trailer + b'\n'
    body += ('startxref\n%d\n%%EOF\n' % xref).encode('ascii')
    return bytes(body)


class ToUnicodeTests(unittest.TestCase):
    def test_two_byte_bfchar_decodes_utf16(self):
        cmap = FileUnicodeMap()
        CMapParser(cmap, StringIO(
            'begincmap\n1 beginbfchar\n<0001> <0041>\nendbfchar\nendcmap\n'
        )).run()
        self.assertEqual(cmap.get_unichr(1), 'A')

    def test_bfrange_string_increments(self):
        cmap = FileUnicodeMap()
        CMapParser(cmap, StringIO(
            'begincmap\n1 beginbfrange\n<0001> <0002> <0041>\nendbfrange\nendcmap\n'
        )).run()
        self.assertEqual(cmap.get_unichr(1), 'A')
        self.assertEqual(cmap.get_unichr(2), 'B')

    def test_identity_h_decodes_character_codes(self):
        decoded = tuple(IdentityCMap(False).decode('\x00\x41\x00\x42'))
        self.assertEqual(decoded, (0x41, 0x42))

    def test_nunpack_accepts_latin1_text(self):
        self.assertEqual(nunpack('\x00\x41'), 0x41)
        self.assertEqual(nunpack('\x01'), 1)


class StreamAndStringTests(unittest.TestCase):
    def test_ascii85_wikipedia_sample(self):
        self.assertEqual(ascii85decode('9jqo^BlbD-BleB1DJ+*+F(f,q'), 'Man is distinguished')
        self.assertEqual(ascii85decode('E,9)oF*2M7/c~>'), 'pleasure.')

    def test_utf16_pdf_string(self):
        raw = '\xfe\xff\x00A\x00B'
        self.assertEqual(decode_text(raw), 'AB')


class StandardEncryptionTests(unittest.TestCase):
    def _open(self, password):
        payload = _pdf(
            [
                (1, b'<< /Type /Catalog /Pages 2 0 R >>'),
                (2, b'<< /Type /Pages /Kids [] /Count 0 >>'),
                (3, b'<< /Filter /Standard /V 1 /R 2 /Length 40 '
                    b'/O (0123456789abcdef0123456789abcdef) '
                    b'/U (0123456789abcdef0123456789abcdef) /P -4 >>'),
            ],
            b'<< /Size 4 /Root 1 0 R /Encrypt 3 0 R '
            b'/ID [<0123456789abcdef0123456789abcdef> '
            b'<0123456789abcdef0123456789abcdef>] >>',
        )
        path = os.path.join(ROOT, 'tests', '_encrypted.pdf')
        try:
            with open(path, 'wb') as handle:
                handle.write(payload)
            parser = PDFParser(py3compat.Latin1File(open(path, 'rb')))
            return PDFDocument(parser, password=password)
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_wrong_password_is_rejected_without_typeerror(self):
        with self.assertRaises(PDFPasswordIncorrect):
            self._open('not-the-password')

    def test_object_key_accepts_text_decrypt_key(self):
        doc = PDFDocument.__new__(PDFDocument)
        doc.decrypt_key = 'abcde'
        out = doc.decrypt_rc4(1, 0, 'Hello')
        self.assertIsInstance(out, str)
        self.assertEqual(len(out), 5)


if __name__ == '__main__':
    unittest.main()
