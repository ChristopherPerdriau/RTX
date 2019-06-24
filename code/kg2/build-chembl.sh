#!/usr/bin/env bash
# build-chembl.sh: download ChEMBL TTL files and gunzip them
# Copyright 2019 Stephen A. Ramsey <stephen.ramsey@oregonstate.edu>

set -o nounset -o pipefail -o errexit

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo Usage: "$0 [all|test]"
    exit 2
fi

echo "================= starting build-chembl.sh ================="
date

CONFIG_DIR=`dirname "$0"`
source ${CONFIG_DIR}/master-config.shinc

CHEMBL_DIR=${BUILD_DIR}/chembl
CHEMBL_VERSION=25
CURL_GET="curl -s -L"
CHEMBL_DB_TARBALL=chembl_${CHEMBL_VERSION}_mysql.tar.gz
MYSQL_DBNAME=chembl_${CHEMBL_VERSION}
CHEMBL_SQL_FILE=${CHEMBL_DIR}/chembl_${CHEMBL_VERSION}/chembl_${CHEMBL_VERSION}_mysql/chembl_${CHEMBL_VERSION}_mysql.dmp

if [[ "${BUILD_FLAG}" == "all" ]]
then
#    mkdir -p ${CHEMBL_DIR}

#    ${CURL_GET} ftp://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/${CHEMBL_DB_TARBALL} > ${CHEMBL_DIR}/${CHEMBL_DB_TARBALL}

#    tar xzf ${CHEMBL_DIR}/${CHEMBL_DB_TARBALL} -C ${CHEMBL_DIR}

    mysql --defaults-extra-file=${MYSQL_CONF} \
          -e "CREATE DATABASE IF NOT EXISTS ${MYSQL_DBNAME} DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_general_ci;"

    mysql --defaults-extra-file=${MYSQL_CONF} --database=${MYSQL_DBNAME} < ${CHEMBL_SQL_FILE}
fi

date
echo "================= script finished ================="