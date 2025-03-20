#!/bin/bash
#
# Author:
# Martin Schilling, 2025, martin.schilling@med.uni-goettingen.de
#
# Submit an input sbatch script to the cluster and archive the JobID.
# Option for saving the script and metadata in a given archive directory.

SCRIPT_DIR="$( cd "$( dirname "$(readlink -f "${BASH_SOURCE[0]}")" )" >/dev/null 2>&1 && pwd )"

helpstr=$(cat <<- EOF
Submit a batch job and create a log file containing the job id.
The sbatch script should follow the format YYYY-MM-DD_sbatch_<suffix>.sbatch.

-a archive	Directory for archiving sbatch script and log file
-h help
EOF
)

REPO_OPTION=()

usage="Usage: $0 [-h] [-a archive_dir] [-r repository_file] <sbatch_file>"

while getopts "a:r:h" opt; do
        case $opt in
	a)
		ARCHIVE_DIR=$(readlink -f "$OPTARG")
	;;
	r)
		REPOSITORY_FILE=$(readlink -f "$OPTARG")
		REPO_OPTION+=(-r "$REPOSITORY_FILE")
	;;
	h)
		echo "$usage"
		echo
		echo "$helpstr"
		exit 0
	;;
        \?)
        	echo "$usage" >&2
		exit 1
        ;;
        esac
done

shift $((OPTIND - 1))

if [ $# -lt 1 ] ; then

        echo "$usage" >&2
        exit 1
fi

INPUT=$(readlink -f "$1")

INPUT_DIR="$( cd "$( dirname "$INPUT" )" >/dev/null 2>&1 && pwd )"

# --- Handle file name ---
FILE_NAME=$(basename "$INPUT")
FILE_NAME=${FILE_NAME%.*}

IFS='_' read -r -a CONTENT <<< "$FILE_NAME"
DATE="${CONTENT[0]}"

read -ra SUFFIX_ARR <<< "${CONTENT[@]:2}"
SUFFIX_STR=$(IFS='_' ; echo "${SUFFIX_ARR[*]}")

LOG_FILE="$DATE"_log_"$SUFFIX_STR".txt
LOG_FILE="$SCRIPT_DIR"/"$LOG_FILE"

# --- Submit job ---
JOB_STRING=$(sbatch "$INPUT")

# --- Extract JobID from output ---
JOB_ID=${JOB_STRING:(-9):(-2)}

if ! [ -f "$LOG_FILE" ] ; then
	printf '%s\n' "$JOB_ID" > "$LOG_FILE"
else
	# append to log file
	sed -i '$a'"$JOB_ID"'' "$LOG_FILE"
fi

if [ "$ARCHIVE_DIR" ] ; then
	bash "$SCRIPT_DIR"/02_archive_scripts.sh -a "$ARCHIVE_DIR" -i "$INPUT_DIR" "$DATE" "$SUFFIX_STR"
	python "$SCRIPT_DIR"/11_write_metadata.py "${REPO_OPTION[@]}" "$ARCHIVE_DIR"
fi
