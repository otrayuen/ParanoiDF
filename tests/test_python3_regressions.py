'''Regression tests for the Python 3 port.

Hex strings, cross-reference streams, and revision-5 encryption used
Python 2 codecs and byte strings. On Python 3 those paths exited the
process or raised TypeError before a PDF could be decrypted.
'''
import hashlib
import os
import unittest

import py3compat
from PDFCore import PDFArray, PDFHexString, PDFNum, PDFParser, PDFStream, PDFString
from PDFCrypto import computeEncryptionKey, isOwnerPass, isUserPass, revision5Password
from PDFFilters import asciiHexEncode


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class HexStringTests(unittest.TestCase):
    def test_hex_string_decodes_to_bytes(self):
        obj = PDFHexString('48656C6C6F')
        self.assertEqual(obj.getValue(), 'Hello')
        self.assertFalse(obj.isFaulty())

    def test_high_bytes_roundtrip(self):
        raw = ''.join(chr(n) for n in range(256))
        encoded = py3compat.hexlify(raw)
        self.assertEqual(py3compat.unhexlify(encoded), raw)
        obj = PDFHexString(encoded)
        self.assertEqual(obj.getValue(), raw)

    def test_xref_stream_fields_decode_as_integers(self):
        # /W [1 2 1]: type 1, offset 16, generation 0
        entry = '\x01\x00\x10\x00'
        f1 = int(py3compat.hexlify(entry[:1]), 16)
        f2 = int(py3compat.hexlify(entry[1:3]), 16)
        f3 = int(py3compat.hexlify(entry[3:]), 16)
        self.assertEqual((f1, f2, f3), (1, 16, 0))

    def test_ascii_hex_filter_encodes(self):
        status, encoded = asciiHexEncode('Hello')
        self.assertEqual(status, 0)
        self.assertEqual(encoded, '48656c6c6f')

    def test_parser_accepts_hex_string_in_document(self):
        pdf = b'''%PDF-1.1
1 0 obj
<< /Type /Catalog /Pages 2 0 R /JS <48656C6C6F> >>
endobj
2 0 obj
<< /Type /Pages /Count 0 >>
endobj
trailer
<< /Size 3 /Root 1 0 R >>
%%EOF
'''
        path = os.path.join(ROOT, 'tests', '_hex_string.pdf')
        try:
            with open(path, 'wb') as handle:
                handle.write(pdf)
            status, parsed = PDFParser().parse(path, forceMode=False, looseMode=False)
        finally:
            if os.path.exists(path):
                os.remove(path)
        self.assertEqual(status, 0)
        values = []

        def walk(obj):
            if obj is None:
                return
            if obj.getType() == 'hexstring':
                values.append(obj.getValue())
            elif obj.getType() in ('dictionary', 'stream'):
                for child in obj.getElements().values():
                    walk(child)
            elif obj.getType() == 'array':
                for child in obj.getElements():
                    walk(child)

        for indirect in parsed.body[0].getObjects().values():
            if indirect is not None:
                walk(indirect.getObject())
        self.assertIn('Hello', values)

    def test_shipped_pdf_with_hex_string_opens(self):
        path = os.path.join(ROOT, 'docs', 'redactTutorial.pdf')
        status, parsed = PDFParser().parse(path, forceMode=False, looseMode=False)
        self.assertEqual(status, 0)
        self.assertIsNotNone(parsed)


class FaultyChildTests(unittest.TestCase):
    def test_array_records_faulty_child_without_crashing(self):
        child = PDFString('hello')
        child.addError('bad child')
        array = PDFArray('[ hello ]', [child])
        self.assertTrue(any('bad child' in error for error in array.getErrors()))

    def test_stream_dictionary_records_faulty_child_without_crashing(self):
        child = PDFString('hello')
        child.addError('bad child')
        with self.assertRaises(Exception) as caught:
            PDFStream('<< /Length 4 /X (hello) >>', 'data', {'/Length': PDFNum('4'), '/X': child})
        self.assertIn('bad child', str(caught.exception))
        self.assertNotIn('valueObject', str(caught.exception))


class Revision5Tests(unittest.TestCase):
    def test_password_is_utf8_truncated_to_127_bytes(self):
        self.assertEqual(revision5Password('secret'), 'secret')
        self.assertEqual(revision5Password('密码'), '密码'.encode('utf-8').decode('latin-1'))
        long_password = 'a' * 200
        self.assertEqual(len(revision5Password(long_password).encode('latin-1')), 127)

    def test_user_check_matches_utf8_bytes(self):
        password = 'héllo'
        salt = 'saltSALT'
        user_string = ('U' * 32) + salt + ('k' * 8)
        digest = hashlib.sha256(password.encode('utf-8') + salt.encode('latin-1')).digest().decode('latin-1')
        self.assertTrue(isUserPass(password, '', digest + user_string[32:], 5))
        self.assertFalse(isUserPass('wrong', '', digest + user_string[32:], 5))

    def test_owner_check_matches_utf8_bytes(self):
        password = 'owner'
        salt = 'saltSALT'
        user_string = 'U' * 48
        digest = hashlib.sha256(
            password.encode('utf-8') + salt.encode('latin-1') + user_string.encode('latin-1')
        ).digest().decode('latin-1')
        owner_string = digest + salt + ('k' * 8)
        self.assertTrue(isOwnerPass(password, owner_string, user_string, '', 256, 5))

    def test_encryption_key_is_derived_for_ascii_and_non_ascii_passwords(self):
        owner = 'O' * 48
        user = 'U' * 48
        owner_encrypted = 'E' * 32
        user_encrypted = 'F' * 32
        file_id = 'ID' * 16
        for password in ('', 'secret', 'héllo', '密码'):
            status, key = computeEncryptionKey(
                password, owner, user, owner_encrypted, user_encrypted,
                file_id, -1028, 256, 5, True, 'USER')
            self.assertEqual(status, 0, password)
            self.assertEqual(len(key), 32)
            status, owner_key = computeEncryptionKey(
                password, owner, user, owner_encrypted, user_encrypted,
                file_id, -1028, 256, 5, True, 'OWNER')
            self.assertEqual(status, 0, password)
            self.assertEqual(len(owner_key), 32)


if __name__ == '__main__':
    unittest.main()
