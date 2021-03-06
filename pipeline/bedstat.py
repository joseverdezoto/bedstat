#!/usr/bin/env python3
"""
bedfile statistics generating pipeline
"""

__author__ = ["Michal Stolarczyk", "Ognen Duzlevski"]
__email__ = "michal@virginia.edu"
__version__ = "0.0.1"

from argparse import ArgumentParser
import json
import yaml
import os

import pypiper
from bbconf.const import *
import bbconf

parser = ArgumentParser(description="A pipeline to read a file in BED format and produce metadata in JSON format.")

parser.add_argument('--bedfile', help='a full path to bed file to process', required=True)
parser.add_argument("--bedbase-config", dest="bedbase_config", type=str, required=False, default=None,
                    help="a path to the bedbase configuratiion file")
parser.add_argument('--nodbcommit', help='whether the json commit to the database should be skipped',
                    action='store_true')
parser.add_argument("-y", "--sample-yaml", dest="sample_yaml", type=str, required=False,
                    help="a yaml config file with sample attributes to pass on more metadata into the database")
parser = pypiper.add_pypiper_args(parser, groups=["pypiper", "common", "looper", "ngs"])

args = parser.parse_args()

bbc = bbconf.BedBaseConf(filepath=bbconf.get_bedbase_cfg(args.bedbase_config))

bedfile_name = os.path.split(args.bedfile)[1]
fileid = os.path.splitext(os.path.splitext(bedfile_name)[0])[0]  # twice since there are 2 exts
outfolder = os.path.abspath(os.path.join(bbc.path.bedstat_output, fileid))

pm = pypiper.PipelineManager(name="bedstat-pipeline", outfolder=outfolder, args=args)
rscript_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "regionstat.R")
assert os.path.exists(rscript_path), FileNotFoundError("'{}' script not found".format(rscript_path))
cmd_vars = dict(rscript=rscript_path, bed=args.bedfile, id=fileid, out=outfolder, genome=args.genome_assembly)
command = "Rscript {rscript} --bedfile={bed} --fileid={id} --outputfolder={out} --genome={genome}".format(**cmd_vars)
json_file_path = os.path.abspath(os.path.join(outfolder, fileid + ".json"))

pm.run(cmd=command, target=json_file_path)

# now get the resulting json file and load it into elasticsearch
# it the file exists, of course
if not args.nodbcommit:
    # open connection to elastic
    bbc.establish_elasticsearch_connection()
    with open(json_file_path, 'r', encoding='utf-8') as f:
        data = json.loads(f.read())
    if args.sample_yaml:
        # get the sample line from the yaml config file
        y = yaml.safe_load(open(args.sample_yaml, "r"))
        # enrich the data from R with the data from the sample line itself
        for key in SEARCH_TERMS:
            try:
                data[key] = y[key]
            except KeyError:
                pm.warning("Can't find key: {}".format(key))
    data[BEDFILE_PATH_KEY] = args.bedfile
    pm.info("Data: {}".format(data))
    bbc.insert_bedfiles_data(data=data)

pm.stop_pipeline()
