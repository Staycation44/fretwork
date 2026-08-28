"""
RESTORE - Restores values from the backup created upon building. Uses your HEADER to find the file
"""

import argparse
import pathlib

import config
import csv
from functions import ini_updater

def restore_from_backup(Header=None, CachePath=None):
    if (CachePath is None):
        CachePath = config.CACHE_DIR

    if (Header is None):
        Header = config.HEADER

    file_name = f"{Header}_BackupData.csv"
    file_path = f"{CachePath}/{file_name}"

    with open(file_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            song_path = row["song_path"]
            difficulty = row["diff_guitar"]

            ini_updater.update_ini_value(f"{song_path}/song.ini", "diff_guitar", difficulty)

def main():
    parser = argparse.ArgumentParser(description="Restore metrics based on original difficulty data")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--path', default=None, help="File path where backup is stored")
    args = parser.parse_args()

    restore_from_backup(args.header, args.path)

if __name__ == '__main__':
    main()