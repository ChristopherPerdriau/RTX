#!/usr/bin/env bash
# delete-mysql-ubuntu.sh: deletes MySQL from an Ubuntu system, including the database(s)
# Copyright 2019 Stephen A. Ramsey <stephen.ramsey@oregonstate.edu>
#
# DANGEROUS: only run this script if you know what you are doing

set -o nounset -o pipefail -o errexit

if [[ $# != 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo Usage: "$0 [all|test]"
    exit 2
fi

sudo apt-get remove --purge -y mysql*
sudo apt-get -y autoremove
sudo apt-get -y autoclean
sudo apt-get remove dbconfig-mysql
sudo rm -r -f /etc/mysql /var/lib/mysql

