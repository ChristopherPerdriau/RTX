#!/usr/bin/env bash
# tsv_to_neo4j.sh: Import TSV files generated from JSON KG into Neo4j
# Copyright 2019 Stephen A. Ramsey
# Author Erica Wood

set -o nounset -o pipefail -o errexit

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo Usage: "$0 <database-name>=graph.db <neo4j-username>=neo4j [test]"
    exit 2
fi

# Usage: tsv_to_neo4j.sh <path_to_directory_containing_tsv_files> <database-name>

echo "================= starting tsv-to-neo4j.sh =================="
date

CONFIG_DIR=`dirname "$0"`
source ${CONFIG_DIR}/master-config.shinc

NEO4J_CONFIG=/etc/neo4j/neo4j.conf
DATABASE_PATH=`grep dbms.directories.data ${NEO4J_CONFIG} | cut -f2 -d=`
DATABASE=${1:-"graph.db"}
USER=${2:-"neo4j"}
BUILD_FLAG=${3:-""}
TSV_DIR=${BUILD_DIR}/TSV

if [[ "${BUILD_FLAG}" == "test" ]]
then
    TEST_ARG="-test"
else
    TEST_ARG=""
fi

# change database and database paths to current database and database path in config file
sudo sed -i '/dbms.active_database/c\dbms.active_database='${DATABASE}'' ${NEO4J_CONFIG}
    
# restart neo4j 
sudo service neo4j restart

# delete the old TSV files if it exists
rm -f kg2-tsv${TEST_ARG}.tar.gz

# create a folder for the TSV files and move the TSV files into them
rm -r -f ${TSV_DIR}
mkdir -p ${TSV_DIR}

# download the latest TSV files from the S3 Bucket
${S3_CP_CMD} s3://${S3_BUCKET}/kg2-tsv${TEST_ARG}.tar.gz ${TSV_DIR}/kg2-tsv${TEST_ARG}.tar.gz

tar -xvzf ${TSV_DIR}/kg2-tsv${TEST_ARG}.tar.gz -C ${TSV_DIR}

# delete the old log file and create a new one
rm -rf ${TSV_DIR}/import.report
touch ${TSV_DIR}/import.report
sudo chown neo4j:adm ${TSV_DIR}/import.report

# stop Neo4j database before deleting the database
sudo service neo4j stop
sudo rm -rf ${DATABASE_PATH}/databases/${DATABASE}

MEM_GB=`${CODE_DIR}/get-system-memory-gb.sh`

# import TSV files into Neo4j as Neo4j
sudo -u neo4j neo4j-admin import --nodes "${TSV_DIR}/nodes_header.tsv,${TSV_DIR}/nodes.tsv" \
    --relationships "${TSV_DIR}/edges_header.tsv,${TSV_DIR}/edges.tsv" \
    --max-memory=${MEM_GB}G --multiline-fields=true --delimiter "\009" \
    --report-file="${TSV_DIR}/import.report" --database=${DATABASE} --ignore-missing-nodes=true

# change read only to false so that indexes and constraints can be added
sudo sed -i '/dbms.read_only/c\dbms.read_only=false' ${NEO4J_CONFIG}
sudo service neo4j start

# wait while neo4j boots up
sleep 1m

# add indexes and constraints to the graph database
${VENV_DIR}/bin/python3 -u ${CODE_DIR}/create_indexes_constraints.py --user ${USER}

# wait for indexing to complete
sleep 5m
sudo service neo4j restart

# change the database to read only
sudo sed -i '/dbms.read_only/c\dbms.read_only=true' ${NEO4J_CONFIG}

sudo service neo4j restart

date
echo "================ script finished ============================"
