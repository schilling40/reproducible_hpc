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

def main(input_dir, output_file, jobid, repository_file):

	if "" == output_file:
		output_file = os.path.join(input_dir, "metadata.json")
		overwrite = False
	else:
		overwrite = True

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

	sbatch_file = os.path.join(input_dir, "sbatch.sbatch")

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

	log_file = os.path.join(input_dir, "log.txt")
	if os.path.isfile(log_file):
		with open (log_file, 'rt', encoding="utf8", errors='ignore') as myfile:
			for line in myfile:
				content = line.strip()
				if 0 != len(content):
					jobid = line.strip().split()[0]
		myfile.close()

	if "" != jobid:
		metadict["jobid"] = jobid
		user_id = subprocess.run(['whoami'], stdout=subprocess.PIPE).stdout.decode('utf-8').strip()

		result = subprocess.run(['reportseff', '-u', user_id], stdout=subprocess.PIPE).stdout.decode('utf-8')

		lines = result.split("\n")
		reports_eff_list = []
		for line in lines:
			contents = line.split()
			if len(contents) > 0 and jobid in contents[0]:
				reports_eff = {"JobID" : contents[0]}
				reports_eff["State"] = contents[1]
				reports_eff["Elapsed"] = contents[2]
				reports_eff["TimeEff"] = contents[3]
				reports_eff["CPUEff"] = contents[4]
				reports_eff["MemEff"] = contents[5]
				reports_eff_list.append(reports_eff)
		metadict["Reportseff"] = reports_eff_list

	if "" != repository_file:
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
							repo_list.append({"repo_name":repo_name, "repo_version":repo_version.strip()})
						else:
							print("Repository path " + repo_path + " could not be resolved.")
			myfile.close()
		metadict["Repositories"] = repo_list

	if not os.path.isfile(output_file) or overwrite:
		json.dump(metadict, open(output_file, 'w'), sort_keys=False, indent='\t', separators=(',', ': '))
	else:
		sys.exit("Output file already exists. Explicitly state the output file to overwrite.")

if __name__ == "__main__":

	parser = argparse.ArgumentParser(
		description="Extract metadata from an sbatch script.")

	parser.add_argument('input_dir', type=str, help="Input directory containing sbatch script.")

	parser.add_argument('-o', "--output", type=str, default="", help="Output file for metadata")
	parser.add_argument('-j', "--jobid", type=str, default = "", help="Job ID")
	parser.add_argument('-r', "--repository_file", type=str, default="", help="File containing information about git repositories in format '<Name>\t<path-to-repository>\n'")
	args = parser.parse_args()

	main(args.input_dir, args.output, args.jobid, args.repository_file)