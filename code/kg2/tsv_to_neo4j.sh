#!/usr/bin/env bash
# tsv_to_neo4j.sh: Import TSV files generated from JSON KG into Neo4j
# Copyright 2019 Stephen A. Ramsey
# Author Erica Wood

set -o nounset -o pipefail -o errexit

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo Usage: "$0 <path_to_directory_containing_tsv_files> <config-file-change [YES|NO]>\
    <database-name> <database-path>"
    exit 2
fi

# Usage: tsv_to_neo4j.sh <path_to_directory_containing_tsv_files> <config-file-change [YES|NO]> <database-name> <database-path>

{
echo "================= starting tsv-to-neo4j.sh =================="
date

TSV_DIR=${1:-"/var/lib/neo4j/import"}
DATABASE=${3:-"graph.db"}
DATABASE_PATH=${4:-"/var/lib/neo4j/data"}
CONFIG_CHANGE=${2:-"NO"}

if [ "${CONFIG_CHANGE}" == "YES" ]
then
    # change database and database paths to current database and database path in config file
    sudo sed -i '/dbms.active_database/c\dbms.active_database='${DATABASE}'' /etc/neo4j/neo4j.conf
    sudo sed -i '/dbms.directories.data/c\dbms.directories.data='${DATABASE_PATH}'' /etc/neo4j/neo4j.conf
    
    # restart neo4j 
    sudo service neo4j restart
fi

# stop Neo4j database before deleting the database
sudo service neo4j stop
sudo rm -rf ${DATABASE_PATH}/databases/${DATABASE}

# import TSV files into Neo4j as Neo4j
sudo -u neo4j neo4j-admin import --nodes "${TSV_DIR}/nodes_header.tsv,${TSV_DIR}/nodes.tsv" \
    --relationships "${TSV_DIR}/edges_header.tsv,${TSV_DIR}/edges.tsv" \
    --max-memory=90G --multiline-fields=true --delimiter "\009" \
    --report-file="${TSV_DIR}/import.report" --database=${DATABASE} --ignore-missing-nodes=true

# start Neo4j database up for use
sudo service neo4j start

date
echo "================ script finished ============================"
} >~/tsv_to_neo4j.log 2>&1
