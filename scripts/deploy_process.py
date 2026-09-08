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
import tempfile
from datetime import date

SETTINGS_FILE = "settings.json"
EXAMPLE_SETTINGS_FILE = "settings.example.json"

REQUIRED_SETTINGS = ("data_dir", "repositories", "models")


def get_script_path():
    # https://stackoverflow.com/questions/4934806/how-can-i-find-scripts-directory
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def load_settings(
    settings_file: str,
) -> dict:
    """Read the JSON file with the paths and names which are specific to a cluster account.

    Args:
        settings_file: Path to the settings file.

    Returns:
        dict: Content of the settings file.
    """
    if not os.path.isfile(settings_file):
        example_file = os.path.join(os.path.dirname(settings_file), EXAMPLE_SETTINGS_FILE)
        raise FileNotFoundError(f"Settings file {settings_file} not found. "
                                f"Copy {example_file} to {settings_file} and adapt the values to your account.")

    with open(settings_file, "r") as myfile:
        try:
            settings = json.load(myfile)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Settings file {settings_file} is not valid JSON: {exc}") from exc

    missing = [key for key in REQUIRED_SETTINGS if key not in settings]
    if missing:
        raise ValueError(f"Settings file {settings_file} is missing the keys: {missing}.")

    return settings


def settings_to_replacements(
    settings: dict,
) -> dict:
    """Flatten the settings into template placeholders.

    Every scalar entry becomes a placeholder under its own key. The 'repositories' entry is flattened
    by one level, so that each repository name becomes a placeholder. All other nested entries,
    such as 'models', give no placeholder.

    Args:
        settings: Output of `load_settings()`.

    Returns:
        dict: Dictionary mapping placeholder names to their replacements.
    """
    replacements = {key: str(value) for key, value in settings.items()
                    if isinstance(value, (str, int, float))}

    for name, path in settings["repositories"].items():
        if name in replacements:
            raise ValueError(f"Repository name '{name}' collides with a top-level key of the settings file.")
        replacements[name] = str(path)

    return replacements


def get_model_path(
    settings: dict,
    group: str,
    version: str,
) -> str:
    """Look up the path of a trained model in the settings.

    Args:
        settings: Output of `load_settings()`.
        group: Model group, one of the keys of the 'models' entry.
        version: Model version within the group.

    Returns:
        str: Path of the trained model.
    """
    models = settings["models"].get(group, {})
    if version not in models:
        raise ValueError(f"Add missing model path. No match for {group} model: {version}. "
                         f"Available versions: {sorted(models)}.")
    return models[version]


def write_repository_file(
    repositories: dict,
    output_file: str,
) -> None:
    """Write the repositories of the settings in the tab-separated format read by `write_metadata.py`.

    Args:
        repositories: Dictionary mapping repository names to their local paths.
        output_file: Path to the output file.
    """
    with open(output_file, "w") as myfile:
        for name, path in repositories.items():
            myfile.write(f"{name}\t{path}\n")


def extract_substrings(
    input_string: str,
) -> list:
    """Extract all substrings encompassed by < and > from the input string.

    Args:
        input_string: The input string containing substrings enclosed in < and >.

    Returns:
        list: A list of extracted substrings.
    """
    pattern = r'<([^>]+)>'
    return re.findall(pattern, input_string)


def replace_substrings(
    lines: list,
    replacement_dict: dict,
) -> tuple:
    """Replace substrings enclosed in < and > based on a dictionary.

    Args:
        lines: Lines of the input file.
        replacement_dict: Dictionary mapping substrings to their replacements.

    Returns:
        tuple of:
            list — the processed lines
            set  — the placeholders without a replacement
    """
    processed = []
    missing = set()

    for line in lines:
        for substr in extract_substrings(line):
            if substr in replacement_dict:
                line = line.replace(f"<{substr}>", str(replacement_dict[substr]))
            else:
                missing.add(substr)
        processed.append(line)

    return processed, missing


def replace_substrings_in_file(
    input_filename: str,
    output_filename: str,
    replacement_dict: dict,
    strict: bool = True,
) -> None:
    """Fill the placeholders of a template file and write the result to a new file.

    The output file is written only after all lines are processed. An incomplete sbatch script must
    never reach the disk, because a later call could submit it.

    Args:
        input_filename: Path to the input file.
        output_filename: Path to the output file.
        replacement_dict: Dictionary mapping substrings to their replacements.
        strict: Raise an error instead of a warning if a placeholder has no replacement.
    """
    with open(input_filename, "r") as input_file:
        lines = input_file.readlines()

    processed, missing = replace_substrings(lines, replacement_dict)

    if missing:
        if strict:
            raise ValueError(f"Unresolved placeholders in template {input_filename}: {sorted(missing)}. "
                             "Add them to the parameter file or to the settings file.")
        for substr in sorted(missing):
            print(f"Warning: no replacement for placeholder <{substr}>.")

    with open(output_filename, "w") as output_file:
        output_file.writelines(processed)

    print(f"Successfully processed {input_filename} and saved output to {output_filename}")


def main(
    input_file: str,
    json_file: str,
    settings_file: str,
    archive_dir: str,
    repository_file: str,
    run_script: bool,
    allow_missing: bool = False,
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

    if "SGN" in input_file:
        stain_position = stains.index("PV")
        replacement_dict["input_key"] = f"setup{stain_position}/timepoint0/s0"
        replacement_dict["masking"] = "sgn"
        replacement_dict["model"] = get_model_path(settings, "SGN", replacement_dict["sgn_version"])

    elif "IHC" in input_file:
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
                replacement_dict["boundary_distance_threshold"] = "0.5"
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

    replace_substrings_in_file(input_file, output_file, replacement_dict, strict=not allow_missing)

    if not run_script:
        print(replacement_dict)
        return

    if archive_dir is None:
        archive_dir = settings.get("archive_dir")

    temporary_repository_file = None
    if repository_file is None:
        handle, repository_file = tempfile.mkstemp(prefix="repository_list_", suffix=".txt", text=True)
        os.close(handle)
        temporary_repository_file = repository_file
        write_repository_file(settings["repositories"], repository_file)

    run_sbatch = os.path.join(get_script_path(), "01_run_sbatch.sh")
    cmd = ["bash", run_sbatch, "-m"]
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

    parser.add_argument("-s", "--settings", type=str, default=os.path.join(get_script_path(), SETTINGS_FILE),
                        help="JSON file with the paths and names of your account. Default: <script dir>/settings.json")
    parser.add_argument("-a", "--archive_dir", type=str, default=None,
                        help="Directory to archive scripts and metadata. Default: archive_dir of the settings file.")
    parser.add_argument("-r", "--repository_file", type=str, default=None,
                        help="File containing git repositories to track. "
                             "Default: derived from the repositories of the settings file.")
    parser.add_argument("--deploy", action="store_true", help="Run script.")
    parser.add_argument("--allow-missing", dest="allow_missing", action="store_true",
                        help="Print a warning instead of raising an error for an unresolved placeholder.")

    args = parser.parse_args()

    try:
        main(args.input, args.json, args.settings, args.archive_dir, args.repository_file,
             args.deploy, args.allow_missing)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(str(exc))
