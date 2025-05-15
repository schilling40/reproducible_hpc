#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Script for extracting metadata from an sbatch script and storing it in a JSON file for better accessibility.
A file containing git repositories can be used as an argument to archive the current git hash of the repository.
"""
import argparse
import json
import os

from typing import Optional

from write_metadata import reportseff_from_jobid


def main(
        input_dir: str,
        pattern: Optional[str] = None,
):
    """Update report of job efficiency, if last status was 'PENDING'.

    Args:
        input_dir: Input directory containing archived scripts.
        pattern: Pattern to match folders in job archive.
    """
    subfolders = [f.path for f in os.scandir(input_dir) if f.is_dir()]

    if pattern is not None:
        subfolders = [s for s in subfolders if pattern in os.path.basename(s)]
        if len(subfolders) == 0:
            raise ValueError(f"No subfolders match pattern {pattern}.")

    overwrite_states = ["RUNNING", "PENDING"]
    update_dir = []

    for folder in subfolders:
        metadata = os.path.join(folder, "metadata.json")
        if os.path.isfile(metadata):
            with open(metadata, 'r') as myfile:
                data = myfile.read()
            metadict = json.loads(data)
            reports = metadict["Reportseff"] if isinstance(metadict["Reportseff"], list) else [metadict["Reportseff"]]
            for report in reports:
                if report["State"] in overwrite_states:
                    update_dir.append(folder)
                    break

    for folder in update_dir:
        print(f"Updating folder {folder}")
        log_file = os.path.join(folder, "log.txt")
        output_file = os.path.join(folder, "metadata.json")

        reportseff_from_jobid(log_file, metadict=metadict, jobid=None)
        json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))

    if len(update_dir) == 0:
        print("All directories contain updated efficiency reports.")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Update report of job efficiency, if last status was 'PENDING'.")

    parser.add_argument('input_dir', type=str, help="Input directory containing sbatch script.")

    parser.add_argument('-p', "--pattern", type=str, default=None,
                        help="Pattern to match folders in job archive.")
    args = parser.parse_args()

    main(args.input_dir, args.pattern)
