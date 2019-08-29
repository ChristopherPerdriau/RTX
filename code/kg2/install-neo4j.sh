#!/bin/bash
# install neo4j into an Ubuntu 18.04 instance and configure it for external network access
# Copyright 2019 Stephen A. Ramsey <stephen.ramsey@oregonstate.edu>

set -o nounset -o pipefail -o errexit

if [[ $# != 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    echo Usage: "$0"
    exit 2
fi

sudo apt-get update -y
sudo apt-get install -y emacs
wget --no-check-certificate -O - https://debian.neo4j.org/neotechnology.gpg.key | sudo apt-key add -
echo 'deb http://debian.neo4j.org/repo stable/' > /tmp/neo4j.list
sudo mv /tmp/neo4j.list /etc/apt/sources.list.d/neo4j.list
sudo apt-get update -y
sudo apt-get install -y neo4j
sudo cp /etc/neo4j/neo4j.conf /etc/neo4j/neo4j.conf.ori

# read -p "Do you want neo4j to be configured for write access? " -n 1 -r
# echo
# if  [[ $REPLY =~ ^[Yy]$ ]]
# then
#     cat /etc/neo4j/neo4j.conf | sed 's/#dbms.read_only=false/dbms.read_only=false/g' > /tmp/neo4j.conf
#     sudo service neo4j stop
#     sudo mv /tmp/neo4j.conf /etc/neo4j
#     sudo service neo4j start
# fi

# read -p "Do you want to configure neo4j for external network access? " -n 1 -r
# echo    # (optional) move to a new line
# if [[ $REPLY =~ ^[Yy]$ ]]
# then
    cat /etc/neo4j/neo4j.conf | sed 's/#dbms.connectors.default_listen_address/dbms.connectors.default_listen_address/g' > /tmp/neo4j.conf
    sudo service neo4j stop
    sudo mv /tmp/neo4j.conf /etc/neo4j
    sudo service neo4j start
# fi

# read -p "Do you want to install Apoc?" -n 1 -r
# echo
# if [[ $REPLY =~ ^[Yy]$ ]]
# then
    cd /tmp
    wget https://github.com/neo4j-contrib/neo4j-apoc-procedures/releases/download/3.5.0.4/apoc-3.5.0.4-all.jar
    sudo service neo4j stop
    sudo mv /tmp/apoc-3.5.0.4-all.jar /var/lib/neo4j/plugins
    cat /etc/neo4j/neo4j.conf | sed 's/#dbms.security.procedures.unrestricted=my.extensions.example,my.procedures.*/dbms.security.procedures.unrestricted=apoc.*/g' > \
                                    /tmp/neo4j.conf
    sudo mv /tmp/neo4j.conf /etc/neo4j
    sudo service neo4j start
# fi

echo "Now you need to go to http://<hostname>:7474 in your browser and set a default password for the database"

