import os
import re

from pathlib import Path

def _tns_dir_if_exists(p: Path) -> Path | None:
    # check common locations relative to a candidate dir
    candidates = [
        p / "network" / "admin" / "tnsnames.ora",
        p / "tnsnames.ora",
    ]
    for c in candidates:
        if c.exists():
            return c.parent
    return None

# we're going to check the most common places you could easily find the tnsnames.ora
# file on a DFO windows image
def get_oracle_path() -> str | None:
    # 1) check TNS_ADMIN first (most explicit)
    tns_admin = os.getenv("TNS_ADMIN")
    if tns_admin:
        tns_dir = _tns_dir_if_exists(Path(tns_admin))
        if tns_dir:
            return str(tns_dir)

    # 2) check ORACLE_HOME next
    oracle_home = os.getenv("ORACLE_HOME")
    if oracle_home:
        tns_dir = _tns_dir_if_exists(Path(oracle_home))
        if tns_dir:
            return str(tns_dir)

    # 3) scan PATH entries for likely oracle/instantclient directories
    path_env = os.getenv("PATH")
    if not path_env:
        return None

    # regexes tuned for common windows layouts (case-insensitive)
    patterns = [
        re.compile(r".*\\oracle\\[^\\]*_x64\\cli", re.IGNORECASE),
        re.compile(r".*\\instantclient[^\\]*", re.IGNORECASE),
        re.compile(r".*\\oracle\\client", re.IGNORECASE),
    ]

    for entry in path_env.split(os.pathsep):
        if not entry:
            continue
        entry = entry.strip('"')  # remove any surrounding quotes
        path_obj = Path(entry)
        # quick check: if PATH entry exists and contains tnsnames.ora
        tns_dir = _tns_dir_if_exists(path_obj)
        if tns_dir:
            return str(tns_dir)

        # try to match known patterns and validate the matched portion
        for rx in patterns:
            m = rx.search(entry)
            if not m:
                continue
            candidate = Path(m.group(0))
            if candidate.exists():
                tns_dir = _tns_dir_if_exists(candidate)
                if tns_dir:
                    return str(tns_dir)
                # also check candidate.parent (sometimes PATH points inside cli)
                parent_tns = _tns_dir_if_exists(candidate.parent)
                if parent_tns:
                    return str(parent_tns)

    return None

# if a tnsnames.ora file can be found this will return a dictionary of TNS names, with a dictionary of the host
# and the port to connect to that database.
#
# databases = scripts.get_tns_file()
# ttran = databases['TTRAN']
# ttran['PORT'] => '1521'
# ttran['HOST'] => db url
def get_tns_file() -> dict:
    if (ora_path := get_oracle_path()) is None:
        return {}

    tns_ora_file = os.path.join(ora_path, 'tnsnames.ora')

    # likely on a windows machine this file will be in the ANSI encoding
    file = open(tns_ora_file, 'r', encoding='ansi')
    data = file.read()

    # remove comments and blank lines
    tns_data = re.sub(r'#[^\n]*\n', '\n', data)
    tns_data = re.sub(r'( *\n *)+', '\n', tns_data.strip())

    # break the string up based on 'db_name ='
    db_name = re.compile(r'(^\w.*?) =')
    db_host = re.compile(r'\(host = (.*?)\)', re.IGNORECASE)
    db_port = re.compile(r'\(port = (.*?)\)', re.IGNORECASE)
    tns_array = tns_data.split('\n')
    databases = {}
    cur_db = None
    for tns in tns_array:
        if db_name.search(tns):
            cur_db = db_name.search(tns).group(1)
            databases[cur_db] = {}
        elif db_host.search(tns):
            databases[cur_db]['HOST'] = db_host.search(tns).group(1)
        elif db_port.search(tns):
            databases[cur_db]['PORT'] = db_port.search(tns).group(1)

    return databases
