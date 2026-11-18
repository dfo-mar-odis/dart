from django.core.management.base import BaseCommand

from bio_tables import sync_tables
from biochem import download
from biochem.download import DatabaseDownloader
from settingsdb import utils
from tqdm import tqdm

import os

class Command(BaseCommand):

    help = "Downloads a Biochem mission and converts it to a Dart database."

    def add_arguments(self, parser):
        parser.add_argument('tns', type=str, help='Biochem server TNS name')
        parser.add_argument('user', type=str, help='Biochem loader account name')
        parser.add_argument('password', type=str, help='Biochem loader password')
        parser.add_argument('mission_seq', type=int, help='Mission Sequence of the mission to download')
        parser.add_argument('-o', '--output', type=str, default="./", help='Location Dart SQLite database will be saved')

    def handle(self, *args, **options):
        tns = options['tns']
        user = options['user']
        password = options['password']
        mission_seq = options['mission_seq']
        output_directory = options['output']

        utils.close_connections()

        if user is None:
            raise EnvironmentError("Missing BIOCHEM_DB_USER")
        if password is None:
            raise EnvironmentError("Missing BIOCHEM_DB_PASS")
        if tns is None:
            raise EnvironmentError("Missing BIOCHEM_DB_NAME")

        sync_tables.connect_tns(user, password, tns)

        # BiochemT test
        # downloader = DatabaseDownloader(20000000010872)

        # BiochemP test
        command_out = self.stdout
        class LogListener(download.Listener):
            progress = None
            def notify(self, message, *args):
                description = message.replace("%d/%d", "")

                if self.progress is None or (self.progress is not None and description != self.progress.desc):
                    self.progress = tqdm(desc=description, unit="")

                if args:
                    if len(args) > 1 and self.progress.total != int(args[1]):
                        self.progress.total = int(args[1])
                    self.progress.update(round(int(args[0])/500, 0))

                # command_out.write(message.replace('%d', '{}').format(*args), ending="\n")

        listener = LogListener()

        downloader = DatabaseDownloader(mission_seq)
        downloader.add_listener(listener)

        location = utils.get_db_location(downloader.db_name, output_directory)
        command_out.write(f"Location: {location}", ending="\n")
        if os.path.exists(location):
            os.remove(location)

        downloader.download()

        utils.close_connections()
