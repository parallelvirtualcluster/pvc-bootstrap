#!/usr/bin/env python3

# db.py - PVC Cluster Auto-bootstrap database libraries
# Part of the Parallel Virtual Cluster (PVC) system
#
#    Copyright (C) 2018-2021 Joshua M. Boniface <joshua@boniface.me>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
###############################################################################

import os
import sqlite3
import contextlib

import pvcbootstrapd.lib.notifications as notifications

from pvcbootstrapd.lib.dataclasses import Cluster, Node

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


#
# Database functions
#
@contextlib.contextmanager
def dbconn(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = 1")
    cur = conn.cursor()
    yield cur
    conn.commit()
    conn.close()


def init_database(config):
    db_path = config["database_path"]
    if not os.path.isfile(db_path):
        print("First run: initializing database.")
        notifications.send_webhook(config, "begin", "First run: initializing database")
        # Initializing the database
        with dbconn(db_path) as cur:
            # Table listing all clusters
            cur.execute(
                """CREATE TABLE clusters
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT UNIQUE  NOT NULL,
                            state TEXT NOT NULL)"""
            )
            # Table listing all nodes
            # FK: cluster -> clusters.id
            cur.execute(
                """CREATE TABLE nodes
                           (id INTEGER PRIMARY KEY AUTOINCREMENT,
                            cluster INTEGER NOT NULL,
                            state TEXT NOT NULL,
                            name TEXT NOT NULL,
                            nodeid INTEGER NOT NULL,
                            bmc_macaddr TEXT NOT NULL,
                            bmc_ipaddr TEXT NOT NULL,
                            host_macaddr TEXT NOT NULL,
                            host_ipaddr TEXT NOT NULL,
                            CONSTRAINT cluster_col FOREIGN KEY (cluster) REFERENCES clusters(id) ON DELETE CASCADE )"""
            )

        notifications.send_webhook(config, "success", "First run: successfully initialized database")


#
# Cluster functions
#
def get_cluster(config, cid=None, name=None):
    if cid is None and name is None:
        return None
    elif cid is not None:
        findfield = "id"
        datafield = cid
    elif name is not None:
        findfield = "name"
        datafield = name

    with dbconn(config["database_path"]) as cur:
        cur.execute(f"""SELECT * FROM clusters WHERE {findfield} = ?""", (datafield,))
        rows = cur.fetchall()

    if len(rows) > 0:
        row = rows[0]
    else:
        return None

    return Cluster(row[0], row[1], row[2])


def add_cluster(config, cspec, name, state):
    with dbconn(config["database_path"]) as cur:
        cur.execute(
            """INSERT INTO clusters
                        (name, state)
                        VALUES
                        (?, ?)""",
            (name, state),
        )

    logger.info(f"New cluster {name} added, populating bootstrap nodes from cspec")
    for bmcmac in cspec["clusters"][name]["cspec_yaml"]["bootstrap"]:
        hostname = cspec["clusters"][name]["cspec_yaml"]["bootstrap"][bmcmac]["node"][
            "hostname"
        ]
        add_node(
            config,
            name,
            hostname,
            int("".join(filter(str.isdigit, hostname))),
            "init",
            bmcmac,
            "",
            "",
            "",
        )
        logger.info(f"Added node {hostname}")

    return get_cluster(config, name=name)


def update_cluster_state(config, name, state):
    with dbconn(config["database_path"]) as cur:
        cur.execute(
            """UPDATE clusters
                        SET state = ?
                        WHERE name = ?""",
            (state, name),
        )

    return get_cluster(config, name=name)


#
# Node functions
#
def get_node(config, cluster_name, nid=None, name=None, bmc_macaddr=None):
    cluster = get_cluster(config, name=cluster_name)

    if nid is None and name is None and bmc_macaddr is None:
        return None
    elif nid is not None:
        findfield = "id"
        datafield = nid
    elif bmc_macaddr is not None:
        findfield = "bmc_macaddr"
        datafield = bmc_macaddr
    elif name is not None:
        findfield = "name"
        datafield = name

    with dbconn(config["database_path"]) as cur:
        cur.execute(
            f"""SELECT * FROM nodes WHERE {findfield} = ? AND cluster = ?""",
            (datafield, cluster.id),
        )
        rows = cur.fetchall()

    if len(rows) > 0:
        row = rows[0]
    else:
        return None

    return Node(
        row[0], cluster.name, row[2], row[3], row[4], row[5], row[6], row[7], row[8]
    )


def get_nodes_in_cluster(config, cluster_name):
    cluster = get_cluster(config, name=cluster_name)

    with dbconn(config["database_path"]) as cur:
        cur.execute("""SELECT * FROM nodes WHERE cluster = ?""", (cluster.id,))
        rows = cur.fetchall()

    node_list = list()
    for row in rows:
        node_list.append(
            Node(
                row[0],
                cluster.name,
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
            )
        )

    return node_list


def add_node(
    config,
    cluster_name,
    name,
    nodeid,
    state,
    bmc_macaddr,
    bmc_ipaddr,
    host_macaddr,
    host_ipaddr,
):
    cluster = get_cluster(config, name=cluster_name)

    with dbconn(config["database_path"]) as cur:
        cur.execute(
            """INSERT INTO nodes
                        (cluster, state, name, nodeid, bmc_macaddr, bmc_ipaddr, host_macaddr, host_ipaddr)
                        VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cluster.id,
                state,
                name,
                nodeid,
                bmc_macaddr,
                bmc_ipaddr,
                host_macaddr,
                host_ipaddr,
            ),
        )

    return get_node(config, cluster_name, name=name)


def update_node_state(config, cluster_name, name, state):
    cluster = get_cluster(config, name=cluster_name)

    with dbconn(config["database_path"]) as cur:
        cur.execute(
            """UPDATE nodes
                        SET state = ?
                        WHERE name = ? AND cluster = ?""",
            (state, name, cluster.id),
        )

    return get_node(config, cluster_name, name=name)


def update_node_addresses(
    config, cluster_name, name, bmc_macaddr, bmc_ipaddr, host_macaddr, host_ipaddr
):
    cluster = get_cluster(config, name=cluster_name)

    with dbconn(config["database_path"]) as cur:
        cur.execute(
            """UPDATE nodes
                        SET bmc_macaddr = ?, bmc_ipaddr = ?, host_macaddr = ?, host_ipaddr = ?
                        WHERE name = ? AND cluster = ?""",
            (bmc_macaddr, bmc_ipaddr, host_macaddr, host_ipaddr, name, cluster.id),
        )

    return get_node(config, cluster_name, name=name)
