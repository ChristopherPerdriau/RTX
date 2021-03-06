#!/usr/bin/env bash
# This script builds a canonicalized version of KG2. If the path to your clone of the RTX repo is not provided as a
# command line argument, it will assume that directory is located at ~/RTX.
# Usage: build-kg2-canonicalized.sh [path_to_your_rtx_directory]

set -e

rtx_dir=${1:-~/RTX}

# Rebuild the NodeSynonymizer using the latest main KG2 (uses the KG2 endpoint specified in RTX/code/config.json)
cd ${rtx_dir}/data/KGmetadata
python3 dumpdata.py
cd ${rtx_dir}/code/ARAX/NodeSynonymizer
python3 sri_node_normalizer.py --build
python3 node_synonymizer.py --build --kg_name=both

# Create the canonicalized KG2 from the main KG2 (uses the KG2 endpoint specified in RTX/code/config.json)
cd ${rtx_dir}/code/kg2/canonicalized
python3 -u create_canonicalized_kg_tsvs.py

# Upload the TSV files to S3
tar -czvf kg2-canonicalized-tsv.tar.gz nodes_c.tsv nodes_c_header.tsv edges_c.tsv edges_c_header.tsv
aws s3 cp --no-progress --region us-west-2 kg2-canonicalized-tsv.tar.gz s3://rtx-kg2/
