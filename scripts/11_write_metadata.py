#!/usr/bin/python
# -- coding: utf-8 --

"""
author: Martin Schilling (martin.schilling@med.uni-goettingen.de), 2025

Script for extracting metadata from an sbatch script and storing it in a JSON file for better accessibility.
A file containing git repositories can be used as an optional argument to archive the current git hash of the repository.
"""

import os, sys
import argparse
import subprocess
import json

def init_metadict(input_dir):
	"""
	Initialize dictionary containing metadata based on the name of the input directory.

	:param str input_dir: The input directory should follow the naming scheme <date>_<suffix>, where the date is formatted as YYYY-MM-DD
	:returns: Dictionary containing date and suffix information
	:rtype: dict
	"""

	input_dir = os.path.abspath(input_dir)

	# evaluate directory name to extract date and suffix
	input_str = input_dir.split("/")[-1]

	contents = input_str.split("_")

	if 2 > len(contents):
		sys.exit("Check correct format of input directory: 'yyy-mm-dd_suffix'.")

	date = contents[0]
	suffix = "_".join(contents[1:])

	metadict = {"date" : date}
	metadict["task"] = suffix
	return metadict

def sbatch_parameters_to_dict(sbatch_file, metadict):
	"""
	Add parameters contained in an sbatch file to an existing dictionary containing metadata.

	:param str sbatch_file: A job script for slumr containing #SBATCH options
	:param dict metadict: Dictionary containing metadata for slurm job
	"""
	pattern = {"#SBATCH"}
	parameter_dict = [	{"param":"--job-name",	"descr":"job-name"},
				{"param":"--mail-user", "descr":"mail-user"},
				{"param":"-t",		"descr":"runtime"},
				{"param":"-p",		"descr":"partition"},
				{"param":"-G",		"descr":"gpu"},
				{"param":"-c",		"descr":"cpus-per-task"},
				{"param":"--mem",	"descr":"Memory-per-node"},
				{"param":"-a",		"descr":"Job array"},
			]

	with open (sbatch_file, 'rt', encoding="utf8", errors='ignore') as myfile:
		for line in myfile:
			if all(s in line for s in pattern):
				contents = line.split(" ")
				for p in parameter_dict:
					if p["param"] == contents[1]:
						metadict[p["descr"]] = contents[2].strip()
					elif p["param"] == contents[1].split("=")[0]:
						metadict[p["descr"]] = contents[1].split("=")[1].strip()
	myfile.close()

def reportseff_from_jobid(log_file, jobid, metadict):
	"""
	Add information about the efficiency of the submitted job to a dictionary containing metadata.
	The information is obtained through the command 'reportseff -u <user-id>' and is available for seven days after job submission.
	The dictionary is only updated, if the JobID was found within the output of the shell command.

	:param str log_file: Text file containing one or multiple lines with JobIDs. Only the last JobID is evaluated.
	:param str jobid: JobID of slurm job
	:param dict metadict: Dictionary containing metadata for slurm job
	"""
	if "" == jobid:
		print("Reading job id from log file")
		if os.path.isfile(log_file):
			with open (log_file, 'rt', encoding="utf8", errors='ignore') as myfile:
				for line in myfile:
					content = line.strip()
					if 0 != len(content):
						jobid = line.strip().split()[0]
			myfile.close()
		else:
			sys.exit("Provide either a JobID or a log file containing a JobID")

	metadict["jobid"] = jobid
	user_id = subprocess.run(['whoami'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()

	result = subprocess.run(['reportseff', '-u', user_id], stdout=subprocess.PIPE).stdout.decode('utf-8')

	lines = result.split("\n")
	reports_eff_list = []
	job_id_found = False

	for line in lines:
		contents = line.split()
		if len(contents) > 0 and jobid in contents[0]:
			job_id_found = True
			reports_eff = {"JobID" : contents[0]}
			reports_eff["State"] = contents[1]
			reports_eff["Elapsed"] = contents[2]
			reports_eff["TimeEff"] = contents[3]
			reports_eff["CPUEff"] = contents[4]
			reports_eff["MemEff"] = contents[5]
			reports_eff_list.append(reports_eff)

	# do not overwrite Reportseff if JobID is not found and entry already exists
	if job_id_found:
		metadict["Reportseff"] = reports_eff_list
	elif "Reportseff" not in metadict:
		metadict["Reportseff"] = []

def repository_status_to_dict(repository_file, metadict):
	"""
	Add information about git repositories to dictionary containing metadata.
	Multiple git repositories can be given within each line containing <repository_name>\t<repository_path>.
	The has of the git commit and the status of the repository ('clean' or 'dirty') are tracked.

	:param str repository_file: File containing name and file path of git repositories.
	:param dict metadict: Dictionary containing metadata.
	"""
	repo_list = []
	if os.path.isfile(repository_file):
		with open (repository_file, 'rt', encoding="utf8", errors='ignore') as myfile:
			for line in myfile:
				content = line.strip().split()
				if 0 != len(content):
					if 2 != len(content):
						sys.exit("Ensure that the file containing repositories has the correct format.")
					else:
						repo_name = content[0]
						repo_path = content[1]
					if os.path.isdir(repo_path):
						repo_version = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, stdout=subprocess.PIPE).stdout.decode('utf-8')
						git_status_out = subprocess.run(["git", "status", "--porcelain"], cwd=repo_path, stdout=subprocess.PIPE).stdout.decode('utf-8')
						if 0 == len(git_status_out):
							git_status = "clean"
						else:
							git_status = "dirty"

						repo_list.append({"repo_name":repo_name, "repo_version":repo_version.strip(), "status":git_status})
					else:
						print("Repository path " + repo_path + " could not be resolved.")
		myfile.close()
	metadict["Repositories"] = repo_list

def main(input_dir, output_file, jobid, repository_file, overwrite):

	if "" == output_file:
		output_file = os.path.join(input_dir, "metadata.json")
	else:
		output_file = os.path.abspath(output_file)

	sbatch_file = os.path.join(input_dir, "sbatch.sbatch")
	log_file = os.path.join(input_dir, "log.txt")

	if os.path.isfile(output_file) and not overwrite:
		with open(output_file, 'r') as myfile:
			data = myfile.read()
		metadict = json.loads(data)
		reportseff_from_jobid(log_file, jobid, metadict=metadict)

	else:
		metadict = init_metadict(input_dir)

		sbatch_parameters_to_dict(sbatch_file, metadict=metadict)
		reportseff_from_jobid(log_file, jobid, metadict=metadict)
		repository_status_to_dict(repository_file, metadict=metadict)

	json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))

if __name__ == "__main__":

	parser = argparse.ArgumentParser(
		description="Extract metadata from an sbatch script.")

	parser.add_argument('input_dir', type=str, help="Input directory containing sbatch script.")

	parser.add_argument('-o', "--output", type=str, default="", help="Output file for metadata. Default: metadata.json")
	parser.add_argument('-j', "--jobid", type=str, default = "", help="JobID")
	parser.add_argument('-r', "--repository_file", type=str, default="", help="File containing information about git repositories in format '<Name>\t<path-to-repository>\n'")
	parser.add_argument("--overwrite", action="store_true", help="Overwrite existing JSOn file.")
	args = parser.parse_args()

	main(args.input_dir, args.output, args.jobid, args.repository_file, args.overwrite)
