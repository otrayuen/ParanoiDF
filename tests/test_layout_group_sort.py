'''Text grouping must not crash when two pairs have the same distance.'''

import unittest

from pdfminer.layout import LTPage, LTTextBoxHorizontal


def box(bbox):
    item = LTTextBoxHorizontal()
    item.set_bbox(bbox)
    return item


class LayoutGroupSortTest(unittest.TestCase):
    def test_equal_spacing_groups_without_comparing_boxes(self):
        page = LTPage(1, (0, 0, 400, 100))
        boxes = [
            box((0, 0, 10, 10)),
            box((30, 0, 40, 10)),
            box((60, 0, 70, 10)),
        ]
        grouped = page.group_textboxes(None, boxes)
        self.assertEqual(len(grouped), 1)


if __name__ == '__main__':
    unittest.main()
