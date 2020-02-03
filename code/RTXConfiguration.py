#!/usr/bin/python3

import re
import os
import sys
import datetime
import json
import time

class RTXConfiguration:

    #### Constructor
    def __init__(self):
        self.version = "RTX 0.5.4"

        file_path = os.path.dirname(os.path.abspath(__file__)) + '/config.json'

        if not os.path.exists(file_path):
            # scp the file
            os.system("scp rtxconfig@arax.rtx.ai:/mnt/temp/config.json " + file_path)
        else:
            now_time = datetime.datetime.now()
            modified_time = time.localtime(os.stat(file_path).st_mtime)
            modified_time = datetime.datetime(*modified_time[:6])
            if (now_time - modified_time).days > 0:
                # scp the file
                os.system("scp rtxconfig@arax.rtx.ai:/mnt/temp/config.json " + file_path)

        f = open(file_path, 'r')
        config_data = f.read()
        f.close()
        self.config = json.loads(config_data)

        # This is the flag/property to switch between the two containers
        self.live = "Production"
        # self.live = "KG2"
        # self.live = "rtxdev"
        # self.live = "staging"
        # self.live = "local"

    #### Define attribute version
    @property
    def version(self) -> str:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def live(self) -> str:
        return self._live

    @live.setter
    def live(self, live: str):
        self._live = live

        if self.live not in self.config.keys():
            self.neo4j_bolt = None
            self.neo4j_database = None
            self.neo4j_username = None
            self.neo4j_password = None
            self.mysql_feedback_host = None
            self.mysql_feedback_port = None
            self.mysql_feedback_username = None
            self.mysql_feedback_password = None
            self.mysql_semmeddb_host = None
            self.mysql_semmeddb_port = None
            self.mysql_semmeddb_username = None
            self.mysql_semmeddb_password = None
            self.mysql_umls_host = None
            self.mysql_umls_port = None
            self.mysql_umls_username = None
            self.mysql_umls_password = None

        else:
            self.neo4j_bolt = self.config[self.live]["neo4j"]["bolt"]
            self.neo4j_database = self.config[self.live]["neo4j"]["database"]
            self.neo4j_username = self.config[self.live]["neo4j"]["username"]
            self.neo4j_password = self.config[self.live]["neo4j"]["password"]
            self.mysql_feedback_host = self.config[self.live]["mysql_feedback"]["host"]
            self.mysql_feedback_port = self.config[self.live]["mysql_feedback"]["port"]
            self.mysql_feedback_username = self.config[self.live]["mysql_feedback"]["username"]
            self.mysql_feedback_password = self.config[self.live]["mysql_feedback"]["password"]
            self.mysql_semmeddb_host = self.config[self.live]["mysql_semmeddb"]["host"]
            self.mysql_semmeddb_port = self.config[self.live]["mysql_semmeddb"]["port"]
            self.mysql_semmeddb_username = self.config[self.live]["mysql_semmeddb"]["username"]
            self.mysql_semmeddb_password = self.config[self.live]["mysql_semmeddb"]["password"]
            self.mysql_umls_host = self.config[self.live]["mysql_umls"]["host"]
            self.mysql_umls_port = self.config[self.live]["mysql_umls"]["port"]
            self.mysql_umls_username = self.config[self.live]["mysql_umls"]["username"]
            self.mysql_umls_password = self.config[self.live]["mysql_umls"]["password"]

        # if self.live == "Production":
        #     self.bolt = "bolt://rtx.ncats.io:7687"
        #     self.database = "rtx.ncats.io:7474/db/data"
        #
        # elif self.live == "KG2":
        #     self.bolt = "bolt://rtx.ncats.io:7787"
        #     self.database = "rtx.ncats.io:7574/db/data"
        #
        # elif self.live == "rtxdev":
        #     self.bolt = "bolt://rtxdev.saramsey.org:7887"
        #     self.database = "rtxdev.saramsey.org:7674/db/data"
        #
        # elif self.live == "staging":
        #     self.bolt = "bolt://steveneo4j.saramsey.org:7687"
        #     self.database = "steveneo4j.saramsey.org:7474/db/data"
        #
        # elif self.live == "local":
        #     self.bolt = "bolt://localhost:7687"
        #     self.database = "localhost:7474/db/data"

        # else:
        #     self.bolt = None
        #     self.database = None

    @property
    def neo4j_bolt(self) -> str:
        return self._neo4j_bolt

    @neo4j_bolt.setter
    def neo4j_bolt(self, bolt: str):
        self._neo4j_bolt = bolt

    @property
    def neo4j_database(self) -> str:
        return self._neo4j_database

    @neo4j_database.setter
    def neo4j_database(self, database: str):
        self._neo4j_database = database

    @property
    def neo4j_username(self) -> str:
        return self._neo4j_username

    @neo4j_username.setter
    def neo4j_username(self, username: str):
        self._neo4j_username = username

    @property
    def neo4j_password(self) -> str:
        return self._neo4j_password

    @neo4j_password.setter
    def neo4j_password(self, password: str):
        self._neo4j_password = password

    @property
    def mysql_feedback_host(self) -> str:
        return self._mysql_feedback_host

    @mysql_feedback_host.setter
    def mysql_feedback_host(self, host: str):
        self._mysql_feedback_host = host

    @property
    def mysql_feedback_port(self) -> str:
        return self._mysql_feedback_port

    @mysql_feedback_port.setter
    def mysql_feedback_port(self, port: str):
        self._mysql_feedback_port = port

    @property
    def mysql_feedback_username(self) -> str:
        return self._mysql_feedback_username

    @mysql_feedback_username.setter
    def mysql_feedback_username(self, username: str):
        self._mysql_feedback_username = username

    @property
    def mysql_feedback_password(self) -> str:
        return self._mysql_feedback_password

    @mysql_feedback_password.setter
    def mysql_feedback_password(self, password: str):
        self._mysql_feedback_password = password

    @property
    def mysql_semmeddb_host(self) -> str:
        return self._mysql_semmeddb_host

    @mysql_semmeddb_host.setter
    def mysql_semmeddb_host(self, host: str):
        self._mysql_semmeddb_host = host

    @property
    def mysql_semmeddb_port(self) -> str:
        return self._mysql_semmeddb_port

    @mysql_semmeddb_port.setter
    def mysql_semmeddb_port(self, port: str):
        self._mysql_semmeddb_port = port

    @property
    def mysql_semmeddb_username(self) -> str:
        return self._mysql_semmeddb_username

    @mysql_semmeddb_username.setter
    def mysql_semmeddb_username(self, username: str):
        self._mysql_semmeddb_username = username

    @property
    def mysql_semmeddb_password(self) -> str:
        return self._mysql_semmeddb_password

    @mysql_semmeddb_password.setter
    def mysql_semmeddb_password(self, password: str):
        self._mysql_semmeddb_password = password

    @property
    def mysql_umls_host(self) -> str:
        return self._mysql_umls_host

    @mysql_umls_host.setter
    def mysql_umls_host(self, host: str):
        self._mysql_umls_host = host

    @property
    def mysql_umls_port(self) -> str:
        return self._mysql_umls_port

    @mysql_umls_port.setter
    def mysql_umls_port(self, port: str):
        self._mysql_umls_port = port

    @property
    def mysql_umls_username(self) -> str:
        return self._mysql_umls_username

    @mysql_umls_username.setter
    def mysql_umls_username(self, username: str):
        self._mysql_umls_username = username

    @property
    def mysql_umls_password(self) -> str:
        return self._mysql_umls_password

    @mysql_umls_password.setter
    def mysql_umls_password(self, password: str):
        self._mysql_umls_password = password


def main():
    rtxConfig = RTXConfiguration()
    # rtxConfig.live = "rtxdev"
    print("RTX Version string: " + rtxConfig.version)
    print("live version: %s" % rtxConfig.live)
    print("neo4j bolt: %s" % rtxConfig.neo4j_bolt)
    print("neo4j databse: %s" % rtxConfig.neo4j_database)
    print("neo4j username: %s" % rtxConfig.neo4j_username)
    print("neo4j password: %s" % rtxConfig.neo4j_password)
    print("mysql feedback host: %s" % rtxConfig.mysql_feedback_host)
    print("mysql feedback port: %s" % rtxConfig.mysql_feedback_port)
    print("mysql feedback username: %s" % rtxConfig.mysql_feedback_username)
    print("mysql feedback password: %s" % rtxConfig.mysql_feedback_password)
    print("mysql semmeddb host: %s" % rtxConfig.mysql_semmeddb_host)
    print("mysql semmeddb port: %s" % rtxConfig.mysql_semmeddb_port)
    print("mysql semmeddb username: %s" % rtxConfig.mysql_semmeddb_username)
    print("mysql semmeddb password: %s" % rtxConfig.mysql_semmeddb_password)
    print("mysql umls host: %s" % rtxConfig.mysql_umls_host)
    print("mysql umls port: %s" % rtxConfig.mysql_umls_port)
    print("mysql umls username: %s" % rtxConfig.mysql_umls_username)
    print("mysql umls password: %s" % rtxConfig.mysql_umls_password)


    # print("bolt protocol: %s" % rtxConfig.bolt)
    # print("database: %s" % rtxConfig.database)
    # print("username: %s" % rtxConfig.username)
    # print("password: %s" % rtxConfig.password)


if __name__ == "__main__":
    main()
