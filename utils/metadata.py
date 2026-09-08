#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Access to the files of an archive folder.
"""
import json
import os

METADATA_FILE = "metadata.json"
SBATCH_FILE = "sbatch.sbatch"
LOG_FILE = "log.txt"


def read_metadata(
    metadata_file: str,
) -> dict:
    """Read a metadata file of an archive folder.

    Args:
        metadata_file: Path to the metadata file.

    Returns:
        dict: Content of the metadata file.
    """
    with open(metadata_file, "r") as myfile:
        return json.loads(myfile.read())


def write_metadata(
    metadict: dict,
    metadata_file: str,
) -> None:
    """Write a metadata file of an archive folder.

    The key order and the tab indentation of the archived files are kept.

    Args:
        metadict: Dictionary containing metadata.
        metadata_file: Path to the metadata file.
    """
    with open(metadata_file, "w") as myfile:
        json.dump(metadict, myfile, sort_keys=False, indent="\t", separators=(",", ": "))


def as_list(
    value,
) -> list:
    """Return a metadata entry which can hold a single entry or a list of entries as a list.

    Args:
        value: Value of a metadata entry.

    Returns:
        list: The value itself if it is a list, otherwise a list with the value as its only entry.
    """
    return value if isinstance(value, list) else [value]


def jobids_from_log(
    log_file: str,
) -> list:
    """Read the JobIDs of a log file, oldest first.

    Args:
        log_file: Text file with one JobID per line.

    Returns:
        list: The JobIDs of the log file. The list is empty if the file does not exist.
    """
    jobids = []

    if os.path.isfile(log_file):
        with open(log_file, "rt", encoding="utf8", errors="ignore") as myfile:
            for line in myfile:
                content = line.strip()
                if len(content) != 0:
                    jobids.append(content.split()[0])

    return jobids


def init_metadict(
    input_dir: str,
) -> dict:
    """Initialise a dictionary with metadata based on the name of the input directory.

    Args:
        input_dir: Archive folder, named after the scheme <date>_<suffix> with the date formatted as YYYY-MM-DD.

    Returns:
        dict: Dictionary containing date and suffix information.
    """
    folder_name = os.path.basename(os.path.abspath(input_dir))
    contents = folder_name.split("_")

    if len(contents) < 2:
        raise ValueError(f"Check correct format of input directory {folder_name}: 'yyyy-mm-dd_suffix'.")

    return {"date": contents[0], "task": "_".join(contents[1:])}
