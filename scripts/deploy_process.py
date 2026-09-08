#!/usr/bin/python
# -- coding: utf-8 --
"""author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Script for executing pre-defined Slurm jobs by giving a set of parameters which are filled into an sbatch script.
The sbatch script is executed and can be archived.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from utils.inputs import check_job_input  # noqa: E402
from utils.repositories import write_repository_file  # noqa: E402
from utils.settings import DEFAULT_SETTINGS_FILE, get_model_path, load_settings, settings_to_replacements  # noqa: E402
from utils.templates import replace_substrings_in_file  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.realpath(__file__))

RUN_SBATCH_SCRIPT = os.path.join(SCRIPTS_DIR, "01_run_sbatch.sh")

# Watershed defaults, used if the model directory has no 'best_best_params.json'.
WATERSHED_DEFAULTS = {
    # default for SGN_v2
    "SGN": {"center_distance_threshold": "0.4",
            "boundary_distance_threshold": "0.5",
            "distance_smoothing": "0"},
    # default for IHC_v4b
    "IHC": {"center_distance_threshold": "0.5",
            "boundary_distance_threshold": "0.6",
            "distance_smoothing": "0.6"},
}


def watershed_parameters(
    model_path: str,
    group: str,
) -> dict:
    """Read the watershed parameters of a trained model.

    Args:
        model_path: Path of the trained model.
        group: Model group, 'SGN' or 'IHC'.

    Returns:
        dict: Watershed parameters. The defaults of the group are used if the model has no parameter file.
    """
    parameter_file = os.path.join(model_path, "best_best_params.json")

    if not os.path.exists(parameter_file):
        return dict(WATERSHED_DEFAULTS.get(group, {}))

    with open(parameter_file, "r") as myfile:
        parameters = json.load(myfile)["params"]

    print(f"Loaded cached best params from {parameter_file}")

    return {key: str(parameters[key]) for key in
            ("center_distance_threshold", "boundary_distance_threshold", "distance_smoothing")}


def main(
    input_file: str,
    json_file: str,
    settings_file: str,
    archive_dir: str,
    repository_file: str,
    run_script: bool,
    allow_missing: bool = False,
    force: bool = False,
):
    settings = load_settings(settings_file)

    with open(json_file, "r") as myfile:
        parameters = json.load(myfile)

    # A parameter of the job overrides the corresponding setting.
    replacement_dict = settings_to_replacements(settings)
    replacement_dict.update(parameters)

    cochlea = replacement_dict["cochlea"]
    replacement_dict["cochlea_job_name"] = "-".join(cochlea.split("_"))

    cochlea_content = cochlea.split("_")
    version = ""
    if len(cochlea_content) < 4:
        raise ValueError("Cochlea parameter does not have the correct format.")
    if len(cochlea_content) > 4:
        if cochlea_content[4][0] != "v":
            raise ValueError("Cochlea parameter does not have the correct format.")
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

    group = ""
    if "SGN" in input_file:
        group = "SGN"
        stain_position = stains.index("PV")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        replacement_dict["masking"] = "sgn"
        replacement_dict["model"] = get_model_path(settings, "SGN", replacement_dict["sgn_version"])

    elif "IHC" in input_file:
        group = "IHC"
        stain_position = stains.index("Vglut3")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        replacement_dict["masking"] = "ihc"
        replacement_dict["model"] = get_model_path(settings, "IHC", replacement_dict["ihc_version"])

    elif "synapse" in input_file:
        stain_position = stains.index("CTBP2")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        if "synapse_version" not in parameters:
            replacement_dict["synapse_version"] = "synapses_v3"
        replacement_dict["model"] = get_model_path(settings, "Synapses", replacement_dict["synapse_version"])

    else:
        replacement_dict["input_key_multi"] = "_".join([f"setup{i}/timepoint0/s0" for i in range(len(stains))])

    if "segment" in input_file:
        replacement_dict.update(watershed_parameters(replacement_dict["model"], group))

    # values for MoBIE transfer
    replacement_dict["channel_multi"] = stains_str

    script_str = os.path.basename(input_file).split(".template")[0]
    cochlea_short = f"{prefix}{number.lstrip('0')}{side}"
    output_file = f"{str(date.today())}_sbatch_{script_str}_{cochlea_short}.sbatch"

    replace_substrings_in_file(input_file, output_file, replacement_dict, strict=not allow_missing)

    warnings = check_job_input(output_file)
    for message in warnings:
        print(f"Warning: {message}")

    if not run_script:
        print(replacement_dict)
        return

    if warnings and not force:
        raise ValueError("The input data of the job does not exist. Use --force to submit the job anyway.")

    if archive_dir is None:
        archive_dir = settings.get("archive_dir")

    temporary_repository_file = None
    if repository_file is None:
        handle, repository_file = tempfile.mkstemp(prefix="repository_list_", suffix=".txt", text=True)
        os.close(handle)
        temporary_repository_file = repository_file
        write_repository_file(settings["repositories"], repository_file)

    cmd = ["bash", RUN_SBATCH_SCRIPT, "-m"]
    if archive_dir:
        cmd += ["-a", archive_dir]
    else:
        print("Warning: no archive directory is set. The job is not archived.")
    cmd += ["-r", repository_file, output_file]

    print(" ".join(cmd))
    try:
        subprocess.run(cmd)
    finally:
        if temporary_repository_file is not None:
            os.remove(temporary_repository_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Fill in a template for an sbatch script using a JSON dictionary. "
        "The new sbatch script is deployed to the cluster and an entry in the archive directory is created.")

    parser.add_argument("-i", "--input", type=str, required=True, help="Input template.")
    parser.add_argument("-j", "--json", type=str, required=True, help="JSON dictionary.")

    parser.add_argument("-s", "--settings", type=str, default=DEFAULT_SETTINGS_FILE,
                        help="JSON file with the paths and names of your account. Default: utils/settings.json")
    parser.add_argument("-a", "--archive_dir", type=str, default=None,
                        help="Directory to archive scripts and metadata. Default: archive_dir of the settings file.")
    parser.add_argument("-r", "--repository_file", type=str, default=None,
                        help="File containing git repositories to track. "
                             "Default: derived from the repositories of the settings file.")
    parser.add_argument("--deploy", action="store_true", help="Run script.")
    parser.add_argument("--allow-missing", dest="allow_missing", action="store_true",
                        help="Print a warning instead of raising an error for an unresolved placeholder.")
    parser.add_argument("--force", action="store_true",
                        help="Deploy the job even if the input data does not exist.")

    args = parser.parse_args()

    try:
        main(args.input, args.json, args.settings, args.archive_dir, args.repository_file,
             args.deploy, args.allow_missing, args.force)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(str(exc))
