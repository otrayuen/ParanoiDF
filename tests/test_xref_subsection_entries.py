'''Xref stream subsections must consume successive entries.

createPDFCrossRefSectionFromStream walked /Index pairs but stored the
next entry cursor in a different name, so the cursor stayed at 0. The
second subsection was filled with the first subsection's entries: a
live object was marked free and the following object kept the wrong
offset. Writing that section back out drops the live object.
'''
import inspect
import os
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import PDFCore
from PDFCore import PDFParser


def _section_from_stream(indirect):
    '''Run the real subsection builder.

    The port still decodes xref fields with str.encode('hex'), which
    Python 3 removed. Swap that call in a copy of the function so this
    test can reach the entry cursor. The cursor itself is the source
    under test.
    '''
    source = textwrap.dedent(inspect.getsource(PDFParser.createPDFCrossRefSectionFromStream))
    source = source.replace(".encode('hex')", ".encode('latin-1').hex()")
    namespace = dict(PDFCore.__dict__)
    exec(source, namespace)
    return namespace['createPDFCrossRefSectionFromStream'](PDFParser(), indirect)


def _xref_stream_pdf(index_clause):
    entries = bytes([
        0, 0, 0, 0,      # object 0, free
        1, 0, 15, 0,     # type 1, offset 15, generation 0
        1, 0, 99, 0,     # type 1, offset 99, generation 0
    ])
    return b'''%PDF-1.5
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Count 0 >>
endobj
3 0 obj
<< /Type /XRef /Size 12 /W [1 2 1] ''' + index_clause + b''' /Root 1 0 R /Length 12 >>
stream
''' + entries + b'''endstream
endobj
startxref
0
%%EOF
'''


class XrefSubsectionEntryTests(unittest.TestCase):
    def _parse_xref_object(self, pdf):
        path = os.path.join(os.path.dirname(__file__), '_xref_subsections.pdf')
        try:
            with open(path, 'wb') as handle:
                handle.write(pdf)
            status, parsed = PDFParser().parse(path, forceMode=False, looseMode=False)
        finally:
            if os.path.exists(path):
                os.remove(path)
        self.assertEqual(status, 0)
        indirect = parsed.getObject(3, indirect=True)
        self.assertIsNotNone(indirect)
        return indirect

    def test_second_subsection_uses_its_own_entries(self):
        indirect = self._parse_xref_object(_xref_stream_pdf(b'/Index [0 1 10 2]'))
        status, section = _section_from_stream(indirect)
        self.assertEqual(status, 0)
        subsections = section.getSubsectionsArray()
        self.assertEqual(len(subsections), 2)

        self.assertEqual(subsections[0].getFirstObject(), 0)
        self.assertEqual(subsections[0].getNumObjects(), 1)
        first = subsections[0].getEntries()
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].getType(), 0)

        self.assertEqual(subsections[1].getFirstObject(), 10)
        self.assertEqual(subsections[1].getNumObjects(), 2)
        second = subsections[1].getEntries()
        self.assertEqual([entry.getType() for entry in second], [1, 1])
        self.assertEqual([entry.getObjectOffset() for entry in second], [15, 99])

    def test_single_subsection_keeps_every_entry(self):
        indirect = self._parse_xref_object(_xref_stream_pdf(b'/Index [0 3]'))
        status, section = _section_from_stream(indirect)
        self.assertEqual(status, 0)
        subsections = section.getSubsectionsArray()
        self.assertEqual(len(subsections), 1)
        self.assertEqual(subsections[0].getFirstObject(), 0)
        entries = subsections[0].getEntries()
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].getType(), 0)
        self.assertEqual([entry.getObjectOffset() for entry in entries[1:]], [15, 99])


if __name__ == '__main__':
    unittest.main()
