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

from utils.inputs import SEGMENTATION_INPUT, check_job_input, job_variables, path_exists  # noqa: E402
from utils.metadata import METADATA_FILE, read_metadata, write_metadata  # noqa: E402
from utils.pipelines import load_pipeline, pipeline_names, step_template, steps_from  # noqa: E402
from utils.repositories import write_repository_file  # noqa: E402
from utils.settings import DEFAULT_SETTINGS_FILE, get_model_path, load_settings, settings_to_replacements  # noqa: E402
from utils.templates import replace_substrings_in_file  # noqa: E402

SCRIPTS_DIR = os.path.dirname(os.path.realpath(__file__))

RUN_SBATCH_SCRIPT = os.path.join(SCRIPTS_DIR, "01_run_sbatch.sh")

# Printed by 01_run_sbatch.sh for the JobID of the submitted job.
JOBID_PREFIX = "SUBMITTED_JOBID="

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


def build_replacements(
    settings: dict,
    parameters: dict,
    input_file: str,
) -> tuple:
    """Build the placeholder replacements of one job.

    Args:
        settings: Output of `load_settings()`.
        parameters: Parameter dictionary of the job.
        input_file: Path of the template. Its name selects the model group and the watershed step.

    Returns:
        tuple of:
            dict — the placeholder replacements
            str  — the short cochlea name used in the output file name
    """
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

    return replacement_dict, f"{prefix}{number.lstrip('0')}{side}"


def render_step(
    input_file: str,
    replacement_dict: dict,
    cochlea_short: str,
    allow_missing: bool = False,
) -> str:
    """Fill a template and write the sbatch script of one job.

    Args:
        input_file: Path of the template.
        replacement_dict: Output of `build_replacements()`.
        cochlea_short: Output of `build_replacements()`.
        allow_missing: Print a warning instead of raising for an unresolved placeholder.

    Returns:
        str: Name of the generated sbatch script.
    """
    script_str = os.path.basename(input_file).split(".template")[0]
    output_file = f"{str(date.today())}_sbatch_{script_str}_{cochlea_short}.sbatch"

    replace_substrings_in_file(input_file, output_file, replacement_dict, strict=not allow_missing)

    return output_file


def check_prediction_absent(
    input_file: str,
    output_file: str,
) -> list:
    """Return a message if an apply step would write into an existing prediction.

    The blocks of the prediction are split over the tasks of the job array, so a second run over an
    existing 'predictions.zarr' leaves a mix of two runs which no later step can detect.

    Args:
        input_file: Path of the template.
        output_file: Path of the generated sbatch script.

    Returns:
        list: Warning messages. The list is empty if the step may run.
    """
    if "apply" not in os.path.basename(input_file):
        return []

    output_folder = job_variables(output_file).get("OUTPUT_FOLDER")
    if output_folder is None:
        return []

    prediction = os.path.join(output_folder, SEGMENTATION_INPUT)
    if not path_exists(prediction):
        return []

    return [f"the prediction of a previous run exists: {prediction}"]


def submit_step(
    output_file: str,
    archive_dir: str,
    repository_file: str,
    dependency: str = None,
) -> str:
    """Submit one job through `01_run_sbatch.sh` and return its JobID.

    Args:
        output_file: Path of the generated sbatch script.
        archive_dir: Directory to archive the job in. No archive is written for an empty value.
        repository_file: File listing the git repositories to snapshot.
        dependency: JobID which has to complete successfully before this job starts.

    Returns:
        str: JobID of the submitted job.
    """
    cmd = ["bash", RUN_SBATCH_SCRIPT, "-m"]
    if archive_dir:
        cmd += ["-a", archive_dir]
    else:
        print("Warning: no archive directory is set. The job is not archived.")
    if dependency is not None:
        cmd += ["-d", dependency]
    cmd += ["-r", repository_file, output_file]

    print(" ".join(cmd))
    # 'capture_output' and 'text' need Python 3.7. The login node of the cluster has Python 3.6.
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        raise ValueError(f"Submission of {output_file} failed with exit code {result.returncode}.")

    for line in result.stdout.splitlines():
        if line.startswith(JOBID_PREFIX):
            return line[len(JOBID_PREFIX):].strip()

    raise ValueError(f"No JobID was reported for {output_file}.")


def write_pipeline_block(
    archive_dir: str,
    output_file: str,
    pipeline_name: str,
    step_index: int,
    step_count: int,
    dependency: str = None,
) -> None:
    """Add the pipeline information to the archived metadata of one step.

    Args:
        archive_dir: Directory the job was archived in.
        output_file: Name of the generated sbatch script.
        pipeline_name: Name of the pipeline.
        step_index: Position of the step in the pipeline, starting at 1.
        step_count: Number of steps of the pipeline.
        dependency: JobID of the previous step, if there is one.
    """
    suffix = os.path.basename(output_file).split(".sbatch")[0].replace("_sbatch_", "_", 1)
    metadata_file = os.path.join(archive_dir, suffix, METADATA_FILE)

    if not os.path.isfile(metadata_file):
        print(f"Warning: no metadata found in {metadata_file}. The pipeline information is not stored.")
        return

    metadict = read_metadata(metadata_file)
    metadict["Pipeline"] = {"name": pipeline_name, "step": step_index, "of": step_count}
    if dependency is not None:
        metadict["Pipeline"]["depends_on"] = dependency

    write_metadata(metadict, metadata_file)


def repository_file_of(
    settings: dict,
    repository_file: str,
) -> tuple:
    """Return the repository file to use, and the temporary file to remove afterwards.

    Args:
        settings: Output of `load_settings()`.
        repository_file: Repository file given on the command line, or None.

    Returns:
        tuple of:
            str — the repository file to use
            str — the temporary file to remove, or None
    """
    if repository_file is not None:
        return repository_file, None

    handle, repository_file = tempfile.mkstemp(prefix="repository_list_", suffix=".txt", text=True)
    os.close(handle)
    write_repository_file(settings["repositories"], repository_file)

    return repository_file, repository_file


def main(
    json_file: str,
    settings_file: str,
    archive_dir: str,
    repository_file: str,
    run_script: bool,
    input_file: str = None,
    pipeline: str = None,
    start_at: str = None,
    allow_missing: bool = False,
    force: bool = False,
):
    settings = load_settings(settings_file)

    with open(json_file, "r") as myfile:
        parameters = json.load(myfile)

    if pipeline is None:
        steps = [input_file]
        pipeline_name = None
        description = None
    else:
        definition = load_pipeline(pipeline)
        pipeline_name = definition["name"]
        description = definition.get("description")
        step_names = definition["steps"]
        if start_at is not None:
            step_names = steps_from(step_names, start_at)
        steps = [step_template(step) for step in step_names]

    if description is not None:
        print(f"Pipeline {pipeline_name}: {description}")

    # Render every step before anything is submitted, so that an unresolved placeholder of a later
    # step cannot leave the earlier steps of the chain queued.
    output_files = []
    for step_file in steps:
        replacement_dict, cochlea_short = build_replacements(settings, parameters, step_file)
        output_files.append(render_step(step_file, replacement_dict, cochlea_short, allow_missing))

    # Only the first step can be checked here. The input of a later step is produced by its
    # predecessor, so it is verified by the guard inside the job script.
    warnings = check_job_input(output_files[0])
    for step_file, output_file in zip(steps, output_files):
        warnings += check_prediction_absent(step_file, output_file)

    for message in warnings:
        print(f"Warning: {message}")

    if len(output_files) > 1:
        for output_file in output_files[1:]:
            print(f"The input of {output_file} is verified when the job runs.")

    if not run_script:
        if pipeline is None:
            print(replacement_dict)
        else:
            print("The pipeline is not deployed. Use --deploy to submit the chain.")
        return

    if warnings and not force:
        raise ValueError("The input data of the job does not exist, or a previous run would be overwritten. "
                         "Use --force to submit the job anyway.")

    if archive_dir is None:
        archive_dir = settings.get("archive_dir")

    repository_file, temporary_repository_file = repository_file_of(settings, repository_file)

    try:
        dependency = None
        for step_index, output_file in enumerate(output_files, start=1):
            jobid = submit_step(output_file, archive_dir, repository_file, dependency)
            print(f"Step {step_index} of {len(output_files)} submitted as JobID {jobid}.")

            if pipeline_name is not None and archive_dir:
                write_pipeline_block(archive_dir, output_file, pipeline_name,
                                     step_index, len(output_files), dependency)

            dependency = jobid
    finally:
        if temporary_repository_file is not None:
            os.remove(temporary_repository_file)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Fill in a template for an sbatch script using a JSON dictionary. "
        "The new sbatch script is deployed to the cluster and an entry in the archive directory is created. "
        "A pipeline fills in one template per step and submits the steps as a chain of Slurm jobs, "
        "where each step starts only after its predecessor completed successfully.")

    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("-i", "--input", type=str, default=None, help="Input template of a single job.")
    source.add_argument("-p", "--pipeline", type=str, default=None,
                        help=f"Name of a pipeline to submit as a chain of jobs. Available: {pipeline_names()}")

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
    parser.add_argument("--start-at", dest="start_at", type=str, default=None,
                        help="Start a pipeline at this step, to resume a chain after a failure.")
    parser.add_argument("--force", action="store_true",
                        help="Deploy the job even if the input data does not exist "
                             "or a previous prediction would be overwritten.")

    args = parser.parse_args()

    if args.start_at is not None and args.pipeline is None:
        parser.error("--start-at needs a pipeline. Use it together with -p.")

    try:
        main(args.json, args.settings, args.archive_dir, args.repository_file, args.deploy,
             args.input, args.pipeline, args.start_at, args.allow_missing, args.force)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(str(exc))
