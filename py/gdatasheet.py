try:
  from xml.etree import ElementTree
except ImportError:
  from elementtree import ElementTree

import re
import gdata.spreadsheet.service

class GDataSheet(object):
    __rc_pattern = re.compile(r'R([0-9]+)C([0-9]+)$')
    def open(self, key, sheet_num=0):
        gd = gdata.spreadsheet.service.SpreadsheetsService()
        gd.source = 'TutorMe'
        sheets = gd.GetWorksheetsFeed(key=key, visibility='public', projection='basic')
        sheet_id = sheets.entry[sheet_num].id.text.rsplit('/', 1)[1]
        self.cells = gd.GetCellsFeed(key=key, wksht_id=sheet_id, visibility='public', projection='basic')

        # the cell ID contains an address in the form of feeds/cells/<key>/<wksheet-id>/public/basic/R1C10
        last_cell = self.cells.entry[len(self.cells.entry)-1]
        self.nrows = int(GDataSheet.__rc_pattern.search(last_cell.id.text).group(1))
        return self
    def rows(self, ncols):
        # drop row 1, the header row
        cur_row = 2
        vals = ncols*[None]

        # Yield each row (1-based index) in turn
        for cell in self.cells.entry:
            # Parse the cell RC address out of its ID
            rc = GDataSheet.__rc_pattern.search(cell.id.text)
            row, col = int(rc.group(1)), int(rc.group(2))
            while cur_row < row:
                yield vals
                cur_row += 1
                vals = ncols*[None]

            # Store contents from cells in the current row
            if cur_row == row and col <= ncols:
                vals[col-1] = cell.content.text

        # return the last row
        yield vals
            
    def close(self):
        pass
