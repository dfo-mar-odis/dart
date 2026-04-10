import csv
from io import BytesIO
from typing import Sequence

from core.parsers.samples.samplefile_parser_abstract import AbstractFileParser


class CSVFileParser(AbstractFileParser):
    tab_names: list = None

    def get_tab_names(self) -> Sequence[str] | None:
        return None

    def find_header_line(self, selected_tab: int = -1) -> tuple[int, Sequence[str]]:
        try:
            content_stream = BytesIO(self.content)
            content_stream.seek(0)
            reader = csv.reader(content_stream.read().decode('utf-8').splitlines())
            for row_idx, row in enumerate(reader, start=1):
                if self._is_header_row(row):
                    return row_idx, row
            raise ValueError("No header line found in the CSV/DAT file")
        except Exception as e:
            raise ValueError(f"Error processing CSV/DAT file: {e}")

    def get_column_names(self, line: int, selected_tab: int = -1) -> list:
        content_stream = BytesIO(self.content)
        content_stream.seek(0)
        reader = csv.reader(content_stream.read().decode('utf-8').splitlines())
        for current_line, row in enumerate(reader, start=1):
            if current_line == line:
                return [cell.strip() for cell in row]  # Return the cells in the specified line

        raise ValueError("No header found in the file.")

