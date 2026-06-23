# sample_parser.py (example; do NOT run outside a Django runtime)
import io
import re
from typing import Optional, Dict, Tuple, Any, List
import pandas as pd
from decimal import Decimal

from django.db import transaction

from settingsdb.models import SampleFileConfig  # config model
from settingsdb.models import SampleFileConfigColumns
from core import models as core_models
from bio_tables import models as bio_models


class ParseResult:
    def __init__(self):
        self.samples_created = 0
        self.values_created = 0
        self.errors: List[str] = []

    def to_dict(self):
        return {
            "samples_created": self.samples_created,
            "values_created": self.values_created,
            "errors": self.errors,
        }


def _read_stream_to_df(fileobj: io.BytesIO, file_config: SampleFileConfig) -> pd.DataFrame:
    """
    Read BytesIO into a pandas DataFrame according to the sample file config.
    - file_config.file_type (expected like 'csv', 'dat', 'xls', 'xlsx')
    - file_config.tab (sheet index for excel)
    - file_config.header_line (zero-based header row)
    """
    # Rewind
    fileobj.seek(0)

    ext = (file_config.file_type or "").lower()
    header = file_config.header_line if file_config.header_line is not None else 0

    if ext in ("xls", "xlsx"):
        # pandas will accept a file-like object for read_excel
        # sheet_name is index or name; we have an int tab index
        df = pd.read_excel(fileobj, sheet_name=file_config.tab, header=header, engine="openpyxl")
    else:
        # default CSV-like
        fileobj.seek(0)
        # Use header parameter: header=row number to use as column names
        df = pd.read_csv(fileobj, header=header, engine="python", dtype=str)
    # Normalize column names to lowercase stripped strings for matching
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def _parse_sample_id(cell_value: Any) -> Optional[Tuple[str, Optional[int]]]:
    """
    Return (base_id_str, replicate_or_None)
    - Handles '123', '123_2' -> ('123', 2)
    - If blank/None -> return None (caller will interpret as blank row)
    """
    if cell_value is None:
        return None
    s = str(cell_value).strip()
    if s == "" or s.lower() in ("nan", "none"):
        return None

    # underscore replicate: last underscore splits replicate if numeric
    if "_" in s:
        base, repl = s.rsplit("_", 1)
        if repl.isdigit():
            return base, int(repl)
        # if not numeric, keep as base name
        return s, None

    # otherwise base id only
    return s, None


def _get_column_definitions(config_columns:list[SampleFileConfigColumns]) -> list[dict[str, Any]]:
    col_defs = []
    for c in config_columns:
        col_defs.append({
            "alias": (c.column_alias or "").strip(),
            "value_col": (c.value_column_name or "").strip().lower(),
            "limit_col": (c.detection_limit_column_name or "").strip().lower() if c.detection_limit_column_name else None,
            "qc_col": (c.quality_control_column_name or "").strip().lower() if c.quality_control_column_name else None,
            "datatype_id": c.datatype_id,
        })

    return col_defs


@transaction.atomic
def parse_sample_file(
    fileobj: io.BytesIO,
    file_config: SampleFileConfig,
    mission: core_models.Mission,
    file_name: Optional[str] = None,
) -> ParseResult:
    """
    Parse a BytesIO stream into core Sample / DiscreteSampleValue records.

    Args:
      - fileobj: BytesIO with the file contents
      - file_config: instance of `settingsdb.models.SampleFileConfig`
      - mission: a `core.models.Mission` instance used to find bottles
      - file_name: optional filename string to store in sample.file

    Returns:
      ParseResult with counts and errors.

    Behavior overview:
      - For each row: determine base sample id and replicate index (explicit via _N or computed for blank rows)
      - Lookup Bottle by bottle_id for the provided mission
      - For every SampleFileConfigColumns defined for the config, create/get the mission sample type and the Sample
        (one Sample per bottle+type), then create a DiscreteSampleValue with replicate, flag, limit and numeric value
    """
    result = ParseResult()

    try:
        df = _read_stream_to_df(fileobj, file_config)
    except Exception as e:
        result.errors.append(f"Failed to read file: {e}")
        return result

    # Lowercase column names expected in the config
    # Todo: sample column cannot be blank, this should probably throw an error needs unit test in
    #  TestSampleFileParserFileConfig
    sample_col_name = (file_config.sample_id_column_name or "").strip().lower()
    comment_col_name = (file_config.comment_column_name or "").strip().lower() if file_config.comment_column_name else None

    # load the configured data columns
    config_columns = list(SampleFileConfigColumns.objects.filter(file_config=file_config).all())
    if not config_columns:
        result.errors.append(f"No SampleFileConfigColumns found for config {file_config}")
        return result

    # Build column definitions: mapping alias -> dict of column names
    col_defs = _get_column_definitions(config_columns)

    # Keep counters/tracking for blanks-based replicates:
    # replicate_counters[(bottle_base_id_str, alias)] = last_replicate_int
    replicate_counters: Dict[Tuple[str, str], int] = {}

    last_seen_base_id: Optional[str] = None

    # Pre-cache BCDataType lookups if datatype_id present
    bcdatatype_cache: Dict[int, bio_models.BCDataType | None] = {}
    for d in set(cd["datatype_id"] for cd in col_defs if cd.get("datatype_id")):
        try:
            bcdatatype_cache[d] = bio_models.BCDataType.objects.get(pk=d)
        except bio_models.BCDataType.DoesNotExist:
            bcdatatype_cache[d] = None

    # Iterate rows
    for idx, row in df.iterrows():
        # extract sample id cell
        sample_cell = row.get(sample_col_name) if sample_col_name else None
        parsed = _parse_sample_id(sample_cell)
        base_id = None
        explicit_replicate = None

        if parsed is None:
            # blank cell
            if file_config.allow_blank_sample_ids and last_seen_base_id is not None:
                base_id = last_seen_base_id
                # the replicate index will be computed per column below using replicate_counters
            else:
                # nothing to attach; skip row (or record error)
                result.errors.append(f"Row {idx+1}: no sample id found and no previous sample to attach as replicate")
                continue
        else:
            base_id, explicit_replicate = parsed
            # normalize base_id if it looks numeric
            base_id = base_id.strip()

        # If this row has an explicit base id then update last_seen_base_id
        if parsed is not None and base_id:
            last_seen_base_id = base_id

        # Convert base_id to int where possible
        bottle_id_val = None
        try:
            # try integer conversion; many projects store bottle ids as integers
            bottle_id_val = int(re.sub(r"\D", "", base_id)) if re.search(r"\d", base_id) else None
        except Exception:
            # fall back to string matching if you store non-numeric bottle ids
            bottle_id_val = None

        # Look up the Bottle in mission
        bottle_qs = None
        bottle = None
        if bottle_id_val is not None:
            bottle_qs = core_models.Bottle.objects.filter(event__mission=mission, bottle_id=bottle_id_val)
            bottle = bottle_qs.first()
        else:
            # try matching on bottle id as string in case they used non-numeric ids (unlikely)
            bottle_qs = core_models.Bottle.objects.filter(event__mission=mission, bottle_id=base_id)
            bottle = bottle_qs.first()

        if not bottle:
            result.errors.append(f"Row {idx+1}: Bottle not found for sample id '{base_id}' (parsed from '{sample_cell}')")
            continue

        # For each configured data column, create sample and discrete value
        for cd in col_defs:
            alias = cd["alias"]
            value_col = cd["value_col"]
            qc_col = cd.get("qc_col")
            limit_col = cd.get("limit_col")

            # Determine replicate index:
            if explicit_replicate is not None:
                replicate_idx = explicit_replicate
            else:
                # compute/increment replicate counter for this bottle+alias
                key = (str(base_id), alias)
                replicate_idx = replicate_counters.get(key, 0) + 1
                replicate_counters[key] = replicate_idx

            if replicate_idx > 1 and not file_config.allow_replicates:
                result.errors.append(f"Row {idx+1} col {value_col}: replicate found for sample '{base_id}' but replicates are disabled")
                continue

            # Fetch the value(s) from the row (some columns may not be present)
            raw_value = None
            if value_col in row.index:
                raw_value = row.get(value_col)
            else:
                result.errors.append(f"Row {idx+1}: expected value column '{value_col}' not found in file")
                continue

            raw_limit = None
            if limit_col:
                raw_limit = row.get(limit_col) if limit_col in row.index else None

            raw_flag = None
            if qc_col:
                raw_flag = row.get(qc_col) if qc_col in row.index else None

            # Interpret value: handle detection limits like "<0.05"
            value_num = None
            limit_num = None
            try:
                if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)) or (isinstance(raw_value, str) and raw_value.strip() == ""):
                    # no direct value; maybe detection limit column exists or value is blank
                    value_num = None
                    # attempt to parse raw_limit below
                else:
                    s = str(raw_value).strip()
                    # if format "<0.05" treat as below detection -> value None, limit = 0.05
                    if s.startswith("<"):
                        value_num = None
                        try:
                            limit_num = Decimal(s.lstrip("<").strip())
                        except Exception:
                            limit_num = None
                    else:
                        # try numeric conversion
                        try:
                            value_num = float(s)
                        except Exception:
                            value_num = None
            except Exception:
                value_num = None

            # If explicit detection limit column present, parse it
            if raw_limit is not None and raw_limit != "" and limit_num is None:
                try:
                    limit_num = Decimal(str(raw_limit).strip())
                except Exception:
                    # if the limit cell contains "<0.01", strip
                    t = str(raw_limit).strip()
                    if t.startswith("<"):
                        try:
                            limit_num = Decimal(t.lstrip("<").strip())
                        except Exception:
                            limit_num = None
                    else:
                        limit_num = None

            # Parse flag if present (int)
            flag_val = None
            if raw_flag is not None and raw_flag != "":
                try:
                    flag_val = int(str(raw_flag).strip())
                except Exception:
                    # non-numeric flags could be mapped here
                    flag_val = None

            # Get or create mission sample type by alias name
            # Name matching: the project's MissionSampleType 'name' field is short_name per mission usage.
            ms_type, created = core_models.MissionSampleType.objects.get_or_create(
                mission=mission,
                name=alias,
                defaults={"long_name": alias, "priority": 1}
            )
            if created:
                result.samples_created += 1
                # attach datatype if config provides datatype_id and it exists
                dtid = cd.get("datatype_id")
                if dtid:
                    dt = bcdatatype_cache.get(dtid)
                    if dt:
                        ms_type.datatype = dt.pk
                        ms_type.save(update_fields=["datatype"])

            # Get/create Sample (one per bottle+type). Samples hold DiscreteSampleValue(s).
            sample_obj, screated = core_models.Sample.objects.get_or_create(
                bottle=bottle,
                type=ms_type,
                defaults={"file": file_name}
            )
            if screated:
                result.samples_created += 1

            # Create discrete value row
            # DiscreteSampleValue fields: sample FK, value (float), replicate (int), flag (int), limit (Decimal)
            dsv_kwargs = {
                "sample": sample_obj,
                "replicate": replicate_idx,
                "flag": flag_val,
                "value": None,
                "limit": None,
                "datatype": None,
                "comment": None
            }
            # Only set fields that accept None as allowed by model
            if value_num is not None:
                dsv_kwargs["value"] = value_num

            if limit_num is not None:
                # DiscreteSampleValue.limit expects DecimalField -> pass Decimal
                dsv_kwargs["limit"] = Decimal(limit_num) if not isinstance(limit_num, Decimal) else limit_num

            try:
                core_models.DiscreteSampleValue.objects.create(**dsv_kwargs)
                result.values_created += 1
            except Exception as e:
                result.errors.append(f"Row {idx+1} alias '{alias}': failed to create DiscreteSampleValue - {e}")

    return result