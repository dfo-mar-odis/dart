import pandas as pd

from typing import Optional, Dict, Tuple, Any, List
from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext as _
from numpy.ma.extras import row_stack

from core import models as core_models
from core.parsers.samples.samplefile_config import FileConfig, FileConfigColumns

from bio_tables import models as bio_models

import logging
logger = logging.getLogger(__name__)
user_logger = logging.getLogger('dart.user')

class ParseResult:
    def __init__(self):
        self.samples_created = 0
        self.values_created = 0
        self.values_updated = 0
        self.errors: List[str] = []

    def to_dict(self):
        return {
            "samples_created": self.samples_created,
            "values_created": self.values_created,
            "values_updated": self.values_updated,
            "errors": self.errors,
        }


def _read_stream_to_df(file_config: FileConfig) -> pd.DataFrame:
    """
    Read BytesIO into a pandas DataFrame according to the FileConfig.
    - file_config.get_file_type() -> e.g. 'CSV', 'XLS', 'DAT'
    - file_config.get_selected_tab() (via get_tab_names/selected_tab) used when reading excel
    - file_config.get_header_line_number() returns header row index (used as pandas header)
    """
    fileobj = file_config.get_parser().content
    fileobj.seek(0)

    ext = (file_config.get_file_type() or "").lower()
    # ask the FileConfig for header line number (fallback to 0)
    try:
        header = file_config.get_header_line_number() - 1
    except Exception:
        header = 0

    # pandas expects header as zero-based row index (or None). We assume FileConfig provides a zero-based value.
    if ext in ("xls", "xlsx", "xlsm"):
        # read_excel accepts file-like objects
        sheet_idx = file_config.get_selected_tab() if hasattr(file_config, "get_selected_tab") else -1
        # if the FileConfig parser uses names instead of integer, pandas accepts names too; keep integer if available
        df = pd.read_excel(fileobj, sheet_name=sheet_idx if sheet_idx >= 0 else 0, header=header, engine="openpyxl")
    else:
        # CSV-like
        fileobj.seek(0)
        df = pd.read_csv(fileobj, header=header, engine="python", dtype=str)

    # Normalize column names to lowercase stripped strings for matching
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _parse_sample_id(cell_value: Any) -> Tuple[int | None, int | None]:
    """
    Return (base_id_str, replicate_or_None)
    - Handles '123', '123_2' -> (123, 2)
    - If blank/None -> return None (caller will interpret as blank row)
    """
    if cell_value is None:
        return None, None
    s = str(cell_value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None, None

    # underscore replicate: last underscore splits replicate if numeric
    if "_" in s:
        base, repl = s.rsplit("_", 1)
        if repl.isdigit():
            return int(base), int(repl)
        # if not numeric, keep as base name
        return int(s), None

    # otherwise base id only
    return int(float(s) if '.' in s else s), None


def _get_column_definitions_from_value_columns(file_config: FileConfig) -> List[dict]:
    """
    Build a list of dicts:
    { alias, value_col (string), limit_col (string|None), qc_col (string|None), datatype_id (None) }
    - FileConfigColumns is index-based (integers). Map indices to column names via file_config.get_column_names()
    - alias: use column name if no alias property available on FileConfigColumns
    """
    col_defs = []
    column_names = file_config.get_column_names() or []
    value_columns: list[FileConfigColumns] = file_config.value_columns or []
    # normalize list entries to str (preserve original names)
    for idx, vc in enumerate(value_columns):
        # each vc expected to be FileConfigColumns-like with integer attributes
        value_col_name = None
        limit_col_name = None
        qc_col_name = None
        alias = None
        datatype: bio_models.BCDataType | None = None

        # value_column is an index
        if getattr(vc, "value_column", None) is not None and vc.value_column >= 0:
            try:
                value_col_name = str(column_names[vc.value_column]).strip().lower()
            except Exception:
                value_col_name = None

        if getattr(vc, "detection_limit_column", None) is not None and vc.detection_limit_column >= 0:
            try:
                limit_col_name = str(column_names[vc.detection_limit_column]).strip().lower()
            except Exception:
                limit_col_name = None

        if getattr(vc, "quality_control_column", None) is not None and vc.quality_control_column >= 0:
            try:
                qc_col_name = str(column_names[vc.quality_control_column]).strip().lower()
            except Exception:
                qc_col_name = None

        if getattr(vc, "datatype_id", -1) != -1:
            try:
                datatype = bio_models.BCDataType.objects.get(pk=vc.datatype_id)
            except Exception as ex:
                logger.exception(ex)
                datatype = None

        # If an alias attribute exists on vc, use it; otherwise fall back to the value column name
        if hasattr(vc, "alias"):
            alias = (vc.alias or "").strip()
        elif datatype:
            alias = datatype.method

        if not alias:
            alias = value_col_name or f"col_{idx}"

        col_defs.append({
            "alias": alias,
            "value_col": value_col_name,
            "limit_col": limit_col_name,
            "qc_col": qc_col_name,
            "datatype_id": datatype.pk if datatype else None,
        })

    return col_defs


@transaction.atomic
def parse_sample_file(
    mission: core_models.Mission,
    file_config: FileConfig,
) -> ParseResult:
    """
    Parse a BytesIO stream into core Sample / DiscreteSampleValue records.

    Args:
      - fileobj: BytesIO with the file contents
      - file_config: instance of `core.parsers.samples.samplefile_config.FileConfig`
      - mission: a `core.models.Mission` instance used to find bottles
      - file_name: optional filename string to store in sample.file

    Returns:
      ParseResult with counts and errors.
    """
    result = ParseResult()

    try:
        df = _read_stream_to_df(file_config)
    except Exception as e:
        result.errors.append(f"Failed to read file: {e}")
        return result

    file_name = file_config.filename

    # Determine sample id / comment column names via FileConfig methods
    sample_col_tuple = file_config.get_sample_id_column() if hasattr(file_config, "get_sample_id_column") else None
    sample_col_name = sample_col_tuple[1].strip().lower() if sample_col_tuple else None

    comment_col_tuple = file_config.get_comment_column() if hasattr(file_config, "get_comment_column") else None
    comment_col_name = comment_col_tuple[1].strip().lower() if comment_col_tuple else None

    # Load configured data columns: must be present as index-based FileConfigColumns on FileConfig.value_columns
    if not getattr(file_config, "value_columns", None):
        result.errors.append("FileConfig has no value_columns defined")
        return result

    col_defs = _get_column_definitions_from_value_columns(file_config)
    if not col_defs:
        result.errors.append("No value columns configured on FileConfig")
        return result

    # Keep counters/tracking for blanks-based replicates:
    replicate_counters: Dict[int, int] = {}
    last_seen_base_id: Optional[int] = None

    mission_sample_types: Dict[(int, int, str), core_models.MissionSampleType] = {}
    existing_samples: Dict[(int, int), core_models.Sample] = {}
    create_discrete_values: List[core_models.DiscreteSampleValue] = []

    # Pre-cache BCDataType lookups -- FileConfig currently doesn't provide datatype ids, so leave empty
    bcdatatype_cache: Dict[int, bio_models.BCDataType | None] = {}

    # Iterate rows
    total_rows = df.shape[0]
    skip_lines = file_config.get_header_line_number()
    for idx, row in df.iterrows():
        row_index = idx + skip_lines + 1 #  used for debug statements

        user_logger.info(_("Processing Sample Row") + ": %d/%d", idx, total_rows)
        sample_cell = row.get(sample_col_name) if sample_col_name else None

        try:
            base_id, r_id = _parse_sample_id(sample_cell)
        except Exception as ex:
            # if the ID is a string and can't be parsed as an int, skip it, but make note in case the issue
            # is a typo that makes the sample ID unparseable
            logger.exception(ex)
            continue

        if base_id is None:
            if not getattr(file_config, "ignore_blank_sample_ids", False):
                if last_seen_base_id is not None:
                    base_id = last_seen_base_id
                else:
                    result.errors.append(f"Row {row_index}: no sample id found and no previous sample to attach as replicate")
                    continue
            else:
                # ignore this row.
                continue
        else:
            last_seen_base_id = base_id

        # Determine replicate index:
        if r_id is not None:
            replicate_idx = r_id
        else:
            replicate_idx = replicate_counters.get(base_id, 0) + 1
            replicate_counters[base_id] = replicate_idx

        if replicate_idx > 1 and not getattr(file_config, "allow_replicates", True):
            result.errors.append(
                f"Row {row_index}: replicate found for sample '{base_id}' but replicates are disabled")
            continue

        comment = row.get(comment_col_name, None) if comment_col_name else None

        # Look up the Bottle in mission
        bottle_qs = core_models.Bottle.objects.filter(event__mission=mission, bottle_id=base_id)
        bottle = bottle_qs.first()

        if not bottle:
            result.errors.append(f"Row {row_index}: Bottle not found for sample id '{base_id}' (parsed from '{sample_cell}')")
            continue

        # For each configured data column, create sample and discrete value
        for cd in col_defs:
            alias = cd["alias"]
            value_col = cd["value_col"]
            qc_col = cd.get("qc_col")
            limit_col = cd.get("limit_col")

            datatype_id = cd.get("datatype_id", None)
            if datatype_id not in bcdatatype_cache:
                bcdatatype_cache[datatype_id] = bio_models.BCDataType.objects.get(pk=datatype_id)
            datatype = bcdatatype_cache[datatype_id]

            # Fetch the value(s) from the row (some columns may not be present)
            raw_value = None
            if value_col in row.index:
                raw_value = row.get(value_col)
            else:
                result.errors.append(f"Row {row_index}: expected value column '{value_col}' not found in file")
                continue

            raw_limit = None
            if limit_col:
                raw_limit = row.get(limit_col) if limit_col in row.index else None

            raw_flag = None
            if qc_col:
                raw_flag = row.get(qc_col) if qc_col in row.index else None

            # Interpret value: handle detection limits like "<0.05"
            value_num = None
            try:
                if str(raw_value).upper() in ["", "NA", "N/A"] or pd.isna(raw_value):
                    if samples:=bottle.samples.filter(type__datatype=datatype.pk):
                        sample = samples.first()
                        if ds_value:=sample.discrete_values.filter(replicate=replicate_idx):
                            ds_value.delete()
                    continue
                elif (raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)) or
                      (isinstance(raw_value, str) and raw_value.strip() == "")):
                    value_num = None
                else:
                    value_num = Decimal(str(raw_value).strip())

            except Exception:
                result.errors.append(f"Row {row_index}: Could not parse value '{raw_value}'")
                continue

            limit_num = None
            if raw_limit is not None and raw_limit != "":
                try:
                    limit_num = Decimal(str(raw_limit).strip())
                    limit_num = None if pd.isna(limit_num) else limit_num
                except Exception:
                    result.errors.append(f"Row {row_index}: Could not parse detection limit '{raw_limit}'")
                    limit_num = None

            flag_val = None
            if raw_flag is not None and raw_flag != "":
                try:
                    flag_val = int(str(raw_flag).strip())
                except Exception:
                    flag_val = None

            mst_key = (mission.pk, datatype.pk if datatype else None, alias)
            if mst_key not in mission_sample_types:
                # Get or create mission sample type by alias name
                ms_type, created = core_models.MissionSampleType.objects.get_or_create(
                    mission=mission,
                    name=alias,
                    datatype=datatype.pk if datatype else None,
                    defaults={"long_name": alias, "priority": 1}
                )
                mission_sample_types[mst_key] = ms_type
                if created:
                    result.samples_created += 1

            ms_type = mission_sample_types[mst_key]

            samp_key = (bottle.pk, ms_type.pk)
            if samp_key not in existing_samples:
                sample_obj, screated = core_models.Sample.objects.get_or_create(
                    bottle=bottle,
                    type=ms_type,
                    defaults={"file": file_name}
                )
                existing_samples[samp_key] = sample_obj
                if screated:
                    result.samples_created += 1

            sample_obj = existing_samples[samp_key]

            # Create discrete value row
            dsv_kwargs = {
                "sample": sample_obj,
                "replicate": replicate_idx,
                "flag": flag_val,
                "value": value_num,
                "limit": limit_num,
                # "datatype": datatype.pk if datatype else None,
                "comment": comment
            }

            try:
                if (dsv := sample_obj.discrete_values.filter(replicate=replicate_idx)).exists():
                    dsv.update(**dsv_kwargs)
                    result.values_updated += 1
                else:
                    create_discrete_values.append(core_models.DiscreteSampleValue(**dsv_kwargs))
                    if len(create_discrete_values) > 100:
                        core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)
                        result.values_created += len(create_discrete_values)
                        create_discrete_values = []
            except Exception as e:
                result.errors.append(f"Row {row_index} alias '{alias}': failed to create DiscreteSampleValue - {e}")

    if len(create_discrete_values) > 0:
        core_models.DiscreteSampleValue.objects.bulk_create(create_discrete_values)
        result.values_created += len(create_discrete_values)

    return result