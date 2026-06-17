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

SGN_MODEL_DIR = "/mnt/vast-nhr/projects/nim00007/data/moser/cochlea-lightsheet/trained_models/SGN"
IHC_MODEL_DIR = "/mnt/vast-nhr/projects/nim00007/data/moser/cochlea-lightsheet/trained_models/IHC"
SYNAPSE_MODEL_DIR = "/mnt/vast-nhr/projects/nim00007/data/moser/cochlea-lightsheet/trained_models/Synapses"

SGN_MODELS = {
    "SGN_v2": os.path.join(SGN_MODEL_DIR, "v2_cochlea_distance_unet_SGN_supervised_2025-05-27"),
}

IHC_MODELS = {
    "IHC_v4b": os.path.join(IHC_MODEL_DIR, "v4_cochlea_distance_unet_IHC_supervised_2025-07-14"),
    "IHC_v5": os.path.join(IHC_MODEL_DIR, "v5_cochlea_distance_unet_IHC_supervised_2025-08-20"),
    "IHC_v6": os.path.join(IHC_MODEL_DIR, "v6_cochlea_distance_unet_IHC_supervised_2025-09-02"),
    "IHC_v7": os.path.join(IHC_MODEL_DIR, "v7_cochlea_distance_unet_IHC_supervised_2025-09-08"),
    "IHC_v9": os.path.join(IHC_MODEL_DIR, "v9_cochlea_distance_unet_IHC_supervised_2026-06-12"),
}

SYNAPSE_MODELS={
    "synapses_v3": os.path.join(SYNAPSE_MODEL_DIR, "synapse_detection_model_v3.pt"),
}


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
    version = ""
    if len(cochlea_content) != 4:
        if cochlea_content[4][0] != "v":
            raise ValueError("Cochlea parameter does not have the correct format.")
        else:
            version = "_" + cochlea_content[4]
            print(f"Processing version {cochlea_content[4]} of cochlea {''.join(cochlea_content[:3])}.")

    animal = cochlea_content[0]
    person = cochlea_content[1]
    number = cochlea_content[2]
    side = cochlea_content[3]
    stains = replacement_dict["stains"]
    stains_str = "_".join(stains)

    prefix = "".join([animal, person])
    replacement_dict["cochlea_data"] = f"{prefix}_{number.lstrip('0')}{side}_{stains_str}_fused{version}.n5"

    if "SGN" in input_file:
        stain_position = stains.index("PV")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        model_version = replacement_dict["sgn_version"]
        replacement_dict["masking"] = "sgn"
        if model_version not in SGN_MODELS.keys():
            raise ValueError(f"Add missing model path. No match for model: {model_version}.")
        replacement_dict["model"] = SGN_MODELS[model_version]

    elif "IHC" in input_file:
        stain_position = stains.index("Vglut3")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        model_version = replacement_dict["ihc_version"]
        replacement_dict["masking"] = "ihc"
        if model_version not in IHC_MODELS.keys():
            raise ValueError(f"Add missing model path. No match for IHC model: {model_version}.")
        replacement_dict["model"] = IHC_MODELS[model_version]

    elif "synapse" in input_file:
        stain_position = stains.index("CTBP2")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        replacement_dict["model"] = SYNAPSE_MODELS["synapses_v3"]

    else:
        replacement_dict["input_key_multi"] = "_".join([f"setup{i}/timepoint0/s0" for i in range(len(stains))])

    if "segment" in input_file:
        watershed_params = os.path.join(replacement_dict["model"], "best_best_params.json")
        if os.path.exists(watershed_params):
            with open(watershed_params) as fh:
                data = json.load(fh)
            print(f"Loaded cached best params from {watershed_params}")
            replacement_dict["center_distance_threshold"] = str(data["params"]["center_distance_threshold"])
            replacement_dict["boundary_distance_threshold"] = str(data["params"]["boundary_distance_threshold"])
            replacement_dict["distance_smoothing"] = str(data["params"]["distance_smoothing"])
        else:
            if "SGN" in input_file:
                # default for SGN_v2
                replacement_dict["center_distance_threshold"] = "0.4"
                replacement_dict["boundary_threshold"] = "0.5"
                replacement_dict["distance_smoothing"] = "0"
            elif "IHC" in input_file:
                # default for IHC_v4b
                replacement_dict["center_distance_threshold"] = "0.5"
                replacement_dict["boundary_distance_threshold"] = "0.6"
                replacement_dict["distance_smoothing"] = "0.6"

    # values for MoBIE transfer
    replacement_dict["channel_multi"] = stains_str

    script_str = os.path.basename(input_file).split(".template")[0]
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
    else:
        print(replacement_dict)


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
