#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Script for extracting metadata from an sbatch script and storing it in a JSON file for better accessibility.
A file containing git repositories can be used as an argument to archive the current git hash of the repository.
"""
import argparse
import json
import os
from datetime import date
from typing import List, Optional

from write_metadata import reportseff_from_jobid
from write_metadata import sbatch_parameters_to_dict


def update_sbatch_data(subfolders: List[str]):
    """Update sbatch_data.

    Args:
        subfolders: List of subfolders containing metadata in the format 'metadata.json'
    """
    update_dir = []

    for folder in subfolders:
        metadata = os.path.join(folder, "metadata.json")
        if os.path.isfile(metadata):
            with open(metadata, 'r') as myfile:
                data = myfile.read()
            metadict = json.loads(data)

            sbatch_file = os.path.join(folder, "sbatch.sbatch")
            sbatch_dict = {}
            sbatch_parameters_to_dict(sbatch_file, sbatch_dict)

            for key, value in sbatch_dict.items():
                if key not in metadict:

                    update_dir.append(folder)
                    metadict[key] = value
                elif value != metadict[key]:
                    update_dir.append(folder)
                    metadict[key] = value

            if folder in update_dir:
                output_file = os.path.join(folder, "metadata.json")
                json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))

    update_dir = list(set(update_dir))
    update_dir.sort()

    for folder in update_dir:
        print(f"Updated sbatch parameters of folder {folder}.")

    if len(update_dir) == 0:
        print("All directories contain updated sbatch information.")


def update_reporteff(subfolders: List[str]):
    """Update efficiency report of previously pending or running tasks.

    Args:
        subfolders: List of subfolders containing metadata in the format 'metadata.json'
    """
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

            # check for dates in the last 8 days
            date_str = [int(i) for i in metadict["date"].split("-")]
            job_date = date(date_str[0], date_str[1], date_str[2])
            days_past = date.today() - job_date
            if len(reports) == 0 and days_past.days <= 8:
                update_dir.append(folder)

    for folder in update_dir:
        print(f"Updating efficiency report of folder {folder}.")
        log_file = os.path.join(folder, "log.txt")
        metadata = os.path.join(folder, "metadata.json")

        with open(metadata, 'r') as myfile:
            data = myfile.read()
        metadict = json.loads(data)
        reportseff_from_jobid(log_file, metadict=metadict, jobid=None)

        output_file = os.path.join(folder, "metadata.json")
        json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))

    if len(update_dir) == 0:
        print("All directories contain updated efficiency reports.")


def check_metadata(subfolders: List[str]):
    """Check metadata of date, task, and JobID.
    If the JobID the last sbatch job (or a previous sbatch job) is not identical to
    the jobID of the efficiency report, the report is deleted.

    Args:
        subfolders: List of subfolders containing metadata in the format 'metadata.json'
    """
    update_metadata = []
    for folder in subfolders:
        folder_name = os.path.basename(folder)
        contents = folder_name.split("_")
        date = contents[0]
        task = "_".join(contents[1:])

        log_file = os.path.join(folder, "log.txt")
        metadata = os.path.join(folder, "metadata.json")

        if os.path.isfile(metadata):
            with open(metadata, 'r') as myfile:
                data = myfile.read()
            metadict = json.loads(data)

            if metadict["date"] != date:
                update_metadata.append(folder)
                metadict["date"] = date

            if metadict["task"] != task:
                metadict["task"] = task
                update_metadata.append(folder)

            def check_old_jobid(log_file, jobid_ref):
                jobids = []
                if os.path.isfile(log_file):
                    with open(log_file, 'rt', encoding="utf8", errors='ignore') as myfile:
                        for line in myfile:
                            content = line.strip()
                            if len(content) != 0:
                                jobid = line.strip().split()[0]
                                jobids.append(jobid)
                if jobid_ref in jobids:
                    return True
                else:
                    return False

            # check if JobID of efficiency report is identical with JobID of log
            reports = metadict["Reportseff"] if isinstance(metadict["Reportseff"], list) else [metadict["Reportseff"]]
            for report in reports:
                if metadict["jobid"] not in report["JobID"]:
                    if not check_old_jobid(log_file, metadict["jobid"]):
                        metadict["Reportseff"] = []
                    reportseff_from_jobid(log_file, metadict, jobid=metadict["jobid"])
                    update_metadata.append(folder)

            output_file = os.path.join(folder, "metadata.json")
            json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))

    update_metadata = list(set(update_metadata))
    update_metadata.sort()

    for folder in update_metadata:
        print(f"Updated essential metadata for {folder}.")


def main(
        input_dir: str,
        pattern: Optional[str] = None,
        check_general_info: bool = False,
        check_sbatch_info: bool = False,
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

    if check_sbatch_info:
        update_sbatch_data(subfolders)

    if check_general_info:
        check_metadata(subfolders)

    update_reporteff(subfolders)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Update report of job efficiency, if last status was 'PENDING'.")

    parser.add_argument('input_dir', type=str, help="Input directory containing sbatch script.")

    parser.add_argument('-p', "--pattern", type=str, default=None,
                        help="Pattern to match folders in job archive.")
    parser.add_argument("--general", action="store_true", help="Check general info.")
    parser.add_argument("--sbatch", action="store_true", help="Check sbatch information.")
    args = parser.parse_args()

    main(args.input_dir, args.pattern, args.general, args.sbatch)
