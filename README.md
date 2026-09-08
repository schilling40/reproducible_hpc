# Scripts to improve reproducibility of HPC

This repository is a collection of scripts connected to the usage of HPC, specifically at the GWDG (Gesellschaft für wissenschaftliche Datenverarbeitung Goettingen).

The goal is to make the usage of HPC resources more reproducible by archiving metadata.

Feedback is appreciated.

## Setup

The paths and names which are specific to a cluster account are collected in `utils/settings.json`.
This file is not tracked by git, so that no absolute path enters the repository.
Copy the example file once and adapt the values to your account:

```
cp utils/settings.example.json utils/settings.json
```

The file contains the mail address and the Slurm account for the sbatch header, the directories of the data and of the job archive, the names of the micromamba environments, the local paths of the git repositories, and the paths of the trained models.
`scripts/deploy_process.py` reads the file and fills the values into the templates.
Use the option `-s` to select a different settings file.

## Repository structure

The directory `scripts` contains the entry points which are run from the command line.
The directory `utils` contains the utility functions which the scripts share, together with the
settings file.

## Current concept

Jobs are submitted to the cluster using a JobID. The JobID has the benefit of being inherently unique, so it could be used as the sole identifier of a script and related data.
However, the number itself is not very informative and a specific task might be started multiple times before achieving a satisfying result.
The current concept involves the usage of a single sbatch script for a specific purpose linked to a date.
It should contain the date and a suffix in the file format `<date>_sbatch_<suffix>` with the date in format `yyyy-mm-dd`, e.g. `2025-03-19_sbatch_apply_unet.sbatch`.
Further scripts might be connected to this script by using the same date and suffix format.

## Archiving metadata
The job information of an sbatch script is monitored and can be looked up using `reportseff -u <user_id>` for around one week after the initial submission.
This information, among other pieces of information from the sbatch script, are extracted using `scripts/write_metadata.py`.

## Template concept
Multiple templates for common sbatch scripts are located in `templates`.
This includes the application of trained neural networks for the segmentation of IHCs and SGNs, the detection of synapses, and the transformation of data into MoBIE format and its transfer to the S3 bucket.
Using `scripts/deploy_process.py` a JSON dictionary with parameters can be given as an input to fill blanks in the templates and use the resulting scripts for job submission.
The templates contain no absolute path.
A blank which is specific to a cluster account is filled from `utils/settings.json`, a blank which is specific to a job is filled from the parameter dictionary.
A blank without a value raises an error, so that no incomplete sbatch script is written.

The input data of the job is checked before the job is deployed.
A missing input gives a warning, and the option `--deploy` stops before the submission.
Use the option `--force` to submit the job for data which does not exist yet.

## Example

An example for a use case showing an sbatch script, a log file containing the JobID, and the corresponding archived metadata are located in the `example` directory.
The example script `example/YYYY-MM-DD_sbatch_example.sbatch` has been adapted from the [GWDG](https://docs.hpc.gwdg.de/how_to_use/slurm/gpu_usage/index.html "GPU Usage - Documentation for HPC").
The text file `example/YYYY-MM-DD_log_example.txt` contains the fictional JobID 1234567, with which the sbatch job has been submitted.
If the script would be started multiple times, the latest jobid would be appended in a new line, if `scripts/01_run_sbatch.sh` is used for submission.

The script and the log file can be archived using the command:
```
bash scripts/02_archive_scripts.sh -i example/ -a example/ YYYY-MM-DD example
```

A file containing information about git repositories can be given as an optional argument to archive the current git hash of the repository.
An example for such a file is `example/repository_list.txt`.
The information about the git repositories should be presented in the format `<Repository-name>	<Path-to-repository>`, where each line corresponds to a new git repository.

The metadata for the script is created with:
```
python scripts/write_metadata.py -r example/repository_list.txt example/YYYY-MM-DD_example/ -o example/YYYY-MM-DD_example/metadata.json
```

