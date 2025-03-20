#!/bin/bash
#
# Author:
# Martin Schilling, 2025, martin.schilling@med.uni-goettingen.de
#
# Archive an sbatch script by copying (or moving) it to another directory.
# The sbatch script should follow the format YYYY-MM-DD_sbatch_<suffiy>.sbatch.
# If not already present, a new folder with the format 'YYYY-MM-DD_<suffix>' is created in the archive directory.

set -e

SCRIPT_REPO="$( cd "$( dirname "$(readlink -f "${BASH_SOURCE[0]}")" )" >/dev/null 2>&1 && pwd )"

# default settings
if [ "$WORK" ] ; then
	INPUT_DIR=$WORK
fi

if [ "$JOB_ARCHIVE" ] ; then
	ARCHIVE_DIR=$JOB_ARCHIVE
fi

TRANSFER_MODE="COPY"

helpstr=$(cat <<- EOF
Archiving data connected to a job on the NHR.
Scripts connected to a job are moved into a separate directory and information about the job is summarized.

-m move		Move files instead of copying them
-i input dir	Input directory containing files connected to the job, starting with the date in format yyyy-mm-dd and ending with a common suffix
-a archive	Archive directory for archiving the scripts
-h help
EOF
)

usage="Usage: $0 [-h] [-m move] [-i input dir] [-a archive_dir] <date> <suffix>"

while getopts "mi:a:h" opt; do
        case $opt in
        m)
                TRANSFER_MODE="MOVE"
        ;;
	i)
		INPUT_DIR=$(readlink -f "$OPTARG")
	;;
	a)
		ARCHIVE_DIR=$(readlink -f "$OPTARG")
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


if [ $# -lt 2 ] ; then

        echo "$usage" >&2
        exit 1
fi

DATE="$1"
SUFFIX="$2"


if [ ! -d "$ARCHIVE_DIR" ] ; then
	echo "Main archive directory does not exist"
	exit 1
fi

if [ ! -d "$INPUT_DIR" ] ; then
	echo "Input directory containing job information does not exist"
	exit 1
fi

ODIR=$ARCHIVE_DIR/"$DATE"_"$SUFFIX"

echo "Script is transferred to directory" "$ODIR"

if [ ! -d "$ODIR" ] ; then
	mkdir -p "$ODIR"
fi

echo "Transfer mode" $TRANSFER_MODE

SBATCH_FILE="$INPUT_DIR"/"$DATE"_sbatch_"$SUFFIX".sbatch
LOG_FILE="$INPUT_DIR"/"$DATE"_log_"$SUFFIX".txt
RUN_FILE="$INPUT_DIR"/"$DATE"_"$SUFFIX".sh

if [ "$TRANSFER_MODE" = "COPY" ] ; then

	cp "$SBATCH_FILE" "$ODIR"/sbatch.sbatch
	cp "$LOG_FILE" "$ODIR"/log.txt
	if [ -f "$RUN_FILE" ] ; then
		cp "$RUN_FILE" "$ODIR"/run.sh
	fi

elif [ "$TRANSFER_MODE" = "MOVE" ] ; then

	mv "$SBATCH_FILE" "$ODIR"/sbatch.sbatch
	mv "$LOG_FILE" "$ODIR"/log.txt
	if [ -f "$RUN_FILE" ] ; then
		mv "$RUN_FILE" "$ODIR"/run.sh
	fi

fi
