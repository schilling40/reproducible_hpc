#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Check that the input data of a job exists before the job is submitted.
"""
import glob
import os
import re

# Written by the apply step. It is the input of the segmentation step.
SEGMENTATION_INPUT = "predictions.zarr"

# Matches 'INPUT=<path>' and 'export OUTPUT_FOLDER=<path>' in a rendered sbatch script.
ASSIGNMENT_PATTERN = re.compile(r"^\s*(?:export\s+)?(INPUT|OUTPUT_FOLDER)=(\S+)")

WILDCARD_CHARACTERS = "*?["


def job_variables(
    sbatch_file: str,
) -> dict:
    """Read the INPUT and OUTPUT_FOLDER assignments of an sbatch script.

    A variable which is assigned more than once keeps the value of the last assignment.

    Args:
        sbatch_file: Path to an sbatch script with all placeholders filled in.

    Returns:
        dict: Dictionary mapping the variable name to its value.
    """
    variables = {}

    with open(sbatch_file, "rt", encoding="utf8", errors="ignore") as myfile:
        for line in myfile:
            match = ASSIGNMENT_PATTERN.match(line)
            if match:
                variables[match.group(1)] = match.group(2).strip("\"'")

    return variables


def path_exists(
    path: str,
) -> bool:
    """Check a path which can contain a wildcard.

    Args:
        path: Path of a file or a directory.

    Returns:
        bool: True if the path exists, or if a wildcard in the path has at least one match.
    """
    if any(character in path for character in WILDCARD_CHARACTERS):
        return len(glob.glob(path)) > 0
    return os.path.exists(path)


def check_job_input(
    sbatch_file: str,
) -> list:
    """Return one message per input of the job which does not exist.

    An INPUT which is not an absolute path is an S3 object key, so it is not checked.
    A job without an INPUT is a segmentation job. Its input is the prediction of the apply
    step inside OUTPUT_FOLDER.

    Args:
        sbatch_file: Path to an sbatch script with all placeholders filled in.

    Returns:
        list: Warning messages. The list is empty if all inputs of the job exist.
    """
    variables = job_variables(sbatch_file)
    input_path = variables.get("INPUT")
    output_folder = variables.get("OUTPUT_FOLDER")

    messages = []

    if input_path is not None:
        if not os.path.isabs(input_path):
            print(f"The input {input_path} is no local path. The check of the input is skipped.")
        elif not path_exists(input_path):
            messages.append(f"the input of the job does not exist: {input_path}")

    elif output_folder is not None:
        prediction = os.path.join(output_folder, SEGMENTATION_INPUT)
        if not path_exists(prediction):
            messages.append(f"the prediction of the apply step does not exist: {prediction}")

    return messages
