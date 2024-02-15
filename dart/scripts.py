import os
import re


# uses the os.getenv('PATH') to locate the oralce home directory to find the tnsnames.ora file
def get_oracle_path():
    path = os.getenv('PATH')
    paths = path.split(os.pathsep)

    ora_path = None
    regexp = re.compile(r'(.*?\\oracle\\.*?_x64)', re.IGNORECASE)
    for path in paths:
        if regexp.search(path.lower()):
            ora_path = regexp.search(path).group(1)
            break

    return ora_path


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

    tns_ora_file = os.path.join(ora_path, 'cli', 'network', 'admin', 'tnsnames.ora')

    file = open(tns_ora_file, 'r')
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
