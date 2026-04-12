from io import BytesIO
from typing import Self, Sequence

from core.parsers.samples.samplefile_parser_abstract import AbstractFileParser
from core.parsers.samples.samplefile_parser_csv_or_dat import CSVFileParser
from core.parsers.samples.samplefile_parser_xls import XLSFileParser


FILE_PARSER_REGISTER = {
    'XLS': XLSFileParser,
    'CSV': CSVFileParser,
    'DAT': CSVFileParser
}

class FileConfigColumns:
    value_column: int = -1
    detection_limit_column: int = -1
    quality_control_column: int = -1


class FileConfig:
    file_type: str
    parser: AbstractFileParser = None

    selected_tab: int = -1
    header_line_number: int = -1

    tab_names: Sequence[str] = None
    column_names: Sequence[str] | None = None

    sample_id_column: int = -1
    comment_column: int = -1
    value_columns: list[FileConfigColumns] | None = None

    allow_replicates: bool = True

    # If blank sample ids are not ignored, that means one row contains the sample ID for the first replicate
    # and if the next row is blank, the previous sample ID should be used, but as an incremented replicate number.
    # Which is the common format for Chlorophyll data.
    # In most cases this won't matter because most data types will have repeated sample IDs or will have a
    # sample ID with an underscore and a number to represent a replicate (e.g 565002_1, 565002_2).
    # The only time this really matters is if we want to ignore values that appear on lines with no sample ID
    # such as with Salinity data where there may be up to 10 lines of data, and line 11 is the average of the runs.
    # Only line 11 will contain a sample ID, we want to ignore the other lines.
    ignore_blank_sample_ids: bool = False

    def _clean_column_names(self):
        if self.column_names is None:
            return

        column_names = list(self.column_names)
        # Remove columns from the end of the list that are 'none'
        while column_names:
            if column_names[-1] is not None:
                break

            column_names.pop()

        # Trim column names to remove white spaces at the start and end of the column name
        self.set_column_names([column_name.strip() for column_name in column_names])


    def _find_column_index(self, column_name_priority_list: Sequence[str]) -> tuple[int, str] | None:
        column_names = self.get_column_names()
        upper_column_names = [(c.upper() if c is not None else '') for c in column_names]
        for scn in column_name_priority_list:
            if scn in upper_column_names:
                index = upper_column_names.index(scn)
                return index, column_names[index]

        return None

    def get_file_type(self):
        return self.file_type

    def get_tab_names(self) -> Sequence[str]:
        if self.tab_names:
            return self.tab_names

        self.set_tab_names(self.parser.get_tab_names())
        return self.tab_names

    def set_tab_names(self, tab_names: Sequence[str]) -> Self:
        self.tab_names = tab_names
        self.set_selected_tab(-1)

        return self

    def set_selected_tab(self, tab: int) -> Self:
        self.selected_tab = tab
        self.set_header_line_number(-1)
        return self

    def get_selected_tab(self) -> int:
        return self.selected_tab

    def set_header_line_number(self, header_line_number: int) -> Self:
        self.header_line_number = header_line_number
        self.set_column_names(None)

        return self

    def get_header_line_number(self) -> int:
        if self.header_line_number >= 0:
            return self.header_line_number

        header = self.parser.find_header_line(self.selected_tab)
        self.header_line_number = header[0]
        self.column_names = header[1]
        self._clean_column_names()

        return self.header_line_number

    def set_column_names(self, column_names: Sequence[str] | None) -> Self:
        self.column_names = column_names
        self.sample_id_column = -1
        self.comment_column = -1
        self.value_columns = None
        return self

    def get_column_names(self) -> Sequence[str]:
        if self.column_names:
            return self.column_names

        line: int = self.get_header_line_number()
        if self.column_names is None and line > 0:
            self.column_names = self.parser.get_column_names(line)
            self._clean_column_names()

        return self.column_names

    def set_sample_id_column(self, sample_id: int) -> Self:
        self.sample_id_column = sample_id
        return self

    def get_sample_id_column(self) -> tuple[int, str] | None:
        if self.sample_id_column >= 0:
            return self.sample_id_column, self.column_names[self.sample_id_column]

        # these expected names are in priority order
        expected_sample_column_names = ['BOTTLE LABEL', 'SAMPLE_ID', 'SAMPLE', 'I.D.']
        return self._find_column_index(expected_sample_column_names)

    def set_comment_column(self, comment_column: int) -> Self:
        self.comment_column = comment_column
        return self

    def get_comment_column(self) -> tuple[int, str] | None:
        if self.comment_column >= 0:
            return self.comment_column, self.column_names[self.comment_column]

        # these expected names are in priority order
        expected_sample_column_names = ['COMMENT', 'COMMENTS']
        return self._find_column_index(expected_sample_column_names)

    def __init__(self, filename, content: BytesIO = None, tab: int = -1):
        self.selected_tab = tab
        self.filename = filename

        # Determine file type based on the file extension
        extension = filename.split('.')[-1].lower()
        if extension == 'csv':
            self.file_type = 'CSV'
        elif extension in ['xls', 'xlsx']:
            self.file_type = 'XLS'
        elif extension == 'dat':
            self.file_type = 'DAT'
        else:
            raise TypeError(f'Unsupported file type: {extension}')

        if content is not None:
            self.parser = FILE_PARSER_REGISTER[self.file_type](content)

    def get_column_index_by_name(self, column_name: str) -> int | None:
        """
        Find the index of a column by its name.

        :param column_name: The name of the column to find.
        :return: The index of the column if found, otherwise None.
        """
        column_names = [c.upper() for c in self.get_column_names()]
        column_name_upper = column_name.upper()
        try:
            return column_names.index(column_name_upper)
        except ValueError:
            return None

    def set_sample_id_column_by_name(self, sample_id_column_name):
        idx = self.get_column_index_by_name(sample_id_column_name)
        if idx is None:
            raise KeyError(f'Sample ID column named {sample_id_column_name} not found.')

        self.set_sample_id_column(idx)

    def set_comment_column_by_name(self, comment_column_name):
        idx = self.get_column_index_by_name(comment_column_name)
        if idx is None:
            raise KeyError(f'Sample ID column named {comment_column_name} not found.')

        self.set_comment_column(idx)
