#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Script for executing pre-defined Slurm jobs by giving a set of parameters which are filled into an sbatch script.
The sbatch script is executed and can be archived.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
# from typing import List, Optional

ARCHIVE_DIR = "/user/schilling40/u15000/job_archive"
REPOSITORY_FILE = "/user/schilling40/u15000/reproducible_hpc/example/repository_list.txt"


def get_script_path():
    # https://stackoverflow.com/questions/4934806/how-can-i-find-scripts-directory
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def extract_substrings(input_string):
    """
    Extract all substrings encompassed by < and > from the input string.

    Args:
        input_string (str): The input string containing substrings enclosed in < and >.

    Returns:
        list: A list of extracted substrings.
    """
    pattern = r'<([^>]+)>'
    return re.findall(pattern, input_string)


def replace_substrings_in_file(input_filename, output_filename, replacement_dict):
    """
    Read a file line by line, replace substrings enclosed in < and > based on a dictionary,
    and write the modified lines to a new file.

    Args:
        input_filename (str): Path to the input file.
        output_filename (str): Path to the output file.
        replacement_dict (dict): Dictionary mapping substrings to their replacements.
    """
    try:
        # Open the input and output files
        with open(input_filename, 'r') as input_file, open(output_filename, 'w') as output_file:
            for line in input_file:
                # Extract substrings from the line
                substrings = extract_substrings(line)

                # Iterate over each substring and replace it if it exists in the dictionary
                for substr in substrings:
                    if substr in replacement_dict:
                        # Use re.sub to replace the first occurrence of the substring
                        # The pattern matches the substring enclosed in < and >
                        pattern = rf'<{re.escape(substr)}>'
                        replacement = replacement_dict[substr]
                        line = re.sub(pattern, replacement, line)

                # Write the modified line to the output file
                output_file.write(line)

        print(f"Successfully processed {input_filename} and saved output to {output_filename}")

    except FileNotFoundError:
        print(f"Input file {input_filename} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


def main(
        input_file,
        json_file,
        archive_dir,
        repository_file,
        run_script,
):
    with open(json_file, 'r') as myfile:
        data = myfile.read()
    replacement_dict = json.loads(data)
    cochlea = replacement_dict["cochlea"]
    replacement_dict["cochlea_job_name"] = "-".join(cochlea.split("_"))

    cochlea_content = cochlea.split("_")
    if len(cochlea_content) != 4:
        raise ValueError("Cochlea parameter does not have the correct format.")
    animal = cochlea_content[0]
    person = cochlea_content[1]
    number = cochlea_content[2]
    side = cochlea_content[3]
    stains = replacement_dict["stains"]
    stains_str = "_".join(stains)

    prefix = "".join([animal, person])
    replacement_dict["cochlea_data"] = f"{prefix}_{number.lstrip('0')}{side}_{stains_str}_fused.n5"

    if "SGN" in input_file:
        stain_position = stains.index("PV")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"

    elif "IHC" in input_file:
        stain_position = stains.index("Vglut3")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"

    elif "synapse" in input_file:
        stain_position = stains.index("CTBP2")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"

    else:
        replacement_dict["input_key_multi"] = "_".join([f"setup{i}/timepoint0/s0" for i in range(len(stains))])

    # values for MoBIE transfer
    replacement_dict["channel_multi"] = stains_str

    script_str = "_".join(os.path.basename(input_file).split("_")[1:]).split(".template")[0]
    cochlea_short = f"{prefix}{number.lstrip('0')}{side}"
    output_file = f"{str(date.today())}_sbatch_{script_str}_{cochlea_short}.sbatch"

    replace_substrings_in_file(input_file, output_file, replacement_dict)

    if run_script:
        # script_dir = os.path.dirname(os.path.realpath(__file__))
        script_dir = get_script_path()
        run_script = os.path.join(script_dir, "01_run_sbatch.sh")
        run_str = f"bash {run_script} -m -a {archive_dir} -r {repository_file} {output_file}"
        print(run_str)
        subprocess.run(["bash", run_script, "-m", "-a", archive_dir, "-r", repository_file, output_file])


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Update report of job efficiency, if last status was 'PENDING'.")

    parser.add_argument('input', type=str, help="Input file.")
    parser.add_argument('json', type=str, help="JSON dictionary.")

    parser.add_argument("-a", "--archive_dir", type=str, default=ARCHIVE_DIR,
                        help="Directory to archive scripts and metadata.")
    parser.add_argument('-r', "--repository_file", type=str, default=REPOSITORY_FILE,
                        help="File containing git repositories to track.")
    parser.add_argument("--deploy", action="store_true", help="Run script.")

    args = parser.parse_args()

    main(args.input, args.json, args.archive_dir, args.repository_file, args.deploy)
