from io import BytesIO
from typing import Sequence

import openpyxl

from core.parsers.samples.samplefile_parser_abstract import AbstractFileParser


class XLSFileParser(AbstractFileParser):
    tab_names: list = None

    def get_tab_names(self) -> Sequence[str] | None:
        if self.tab_names:
            return self.tab_names

        try:
            workbook = openpyxl.load_workbook(BytesIO(self.content), read_only=True)
            self.tab_names = workbook.sheetnames
            return self.tab_names
        except Exception as e:
            raise ValueError(f"Error reading XLS file: {e}")

    def find_header_line(self, selected_tab: int = -1) -> tuple[int, Sequence[str]]:
        tab_names = self.get_tab_names()
        tab_name = tab_names[selected_tab] if selected_tab != -1 else tab_names[0]
        try:
            workbook = openpyxl.load_workbook(BytesIO(self.content), read_only=True)
            sheet = workbook[tab_name]
            for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                if self._is_header_row(row):
                    return row_idx, [cell for cell in row]
            raise ValueError("No header line found in the Excel file")
        except Exception as e:
            raise ValueError(f"Error processing Excel file: {e}")

    def get_column_names(self, line: int, selected_tab: int = -1) -> Sequence[str]:
        tab_names = self.get_tab_names()
        tab_name = tab_names[selected_tab] if selected_tab != -1 else tab_names[0]
        try:
            workbook = openpyxl.load_workbook(BytesIO(self.content), read_only=True)
            sheet = workbook[tab_name]
            row = sheet[line]
            return [cell.value for cell in row]
        except IndexError:
            raise ValueError(f"Row {line} does not exist in the sheet '{tab_name}'.")
        except KeyError:
            raise ValueError(f"Sheet '{tab_name}' does not exist in the Excel file.")
        except Exception as e:
            raise ValueError(f"Error reading Excel file: {e}")

