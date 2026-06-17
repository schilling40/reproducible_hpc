# Scripts to improve reproducibility of HPC

This repository is a collection of scripts connected to the usage of HPC, specifically at the GWDG (Gesellschaft für wissenschaftliche Datenverarbeitung Goettingen).

The goal is to make the usage of HPC resources more reproducible by archiving metadata.

Feedback is appreciated.

## Current concept

Jobs are submitted to the cluster using a JobID. The JobID has the benefit of being inherently unique, so it could be used as the sole identifier of a script and related data.
However, the number itself is not very informative and a specific task might be started multiple times before achieving a satisfying result.
The current concept involves the usage of a single sbatch script for a specific purpose linked to a date.
It should contain the date and a suffix in the file format `<date>_sbatch_<suffix>` with the date in format `yyyy-mm-dd`, e.g. `2025-03-19_sbatch_apply_unet.sbatch`.
Further scripts might be connected to this script by using the same date and suffix format.


## Template concept
Multiple templates are located in `templates`. Using `scripts/deploy_process.py` a JSON dictionary with parameters can be given as an input to fill blanks in the templates and use the resulting scripts for job submission.

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

