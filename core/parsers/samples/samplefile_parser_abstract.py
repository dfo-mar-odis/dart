from io import BytesIO
from typing import Sequence


class AbstractFileParser:
    content: bytes = None

    def get_tab_names(self) -> Sequence[str] | None:
        raise NotImplementedError

    def get_column_names(self, line: int, selected_tab: int = -1) -> Sequence[str]:
        """
        Get the data on a specific row of a file.
        :param line: The row number to retrieve (1-based index).
        :param selected_tab: The tab number to retrieve if used by the parser.
        :return: A list of cell values in the specified row.
        """
        raise NotImplementedError

    def find_header_line(self, selected_tab: int = -1) -> tuple[int, Sequence[str]]:
        raise NotImplementedError

    def _is_header_row(self, row) -> bool:
        # A heuristic to determine if a row is a header row
        if not row:
            return False
        # Check if the row has a significant number of non-empty text cells
        text_count = sum(1 for cell in row if isinstance(cell, str) and cell.strip())
        # Check if the row has a reasonable number of columns (e.g., > 3)
        return text_count > len(row) / 2 and len(row) > 3

    def __init__(self, content: BytesIO):
        self.content = content.read()