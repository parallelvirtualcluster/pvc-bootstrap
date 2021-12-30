#!/usr/bin/env python3

# pvcbootstrapd.py - PVC Cluster Auto-bootstrap
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

import flask
import json

from pvcbootstrapd.Daemon import config

import pvcbootstrapd.lib.lib as lib

from flask_restful import Resource, Api
from celery import Celery
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)


# Create Flask app and set config values
app = flask.Flask(__name__)
blueprint = flask.Blueprint("api", __name__, url_prefix="")
api = Api(blueprint)
app.register_blueprint(blueprint)

app.config[
    "CELERY_BROKER_URL"
] = f"redis://{config['queue_address']}:{config['queue_port']}{config['queue_path']}"

celery = Celery(app.name, broker=app.config["CELERY_BROKER_URL"])
celery.conf.update(app.config)


#
# Celery functions
#
@celery.task(bind=True)
def dnsmasq_checkin(self, data):
    lib.dnsmasq_checkin(config, data)


@celery.task(bind=True)
def host_checkin(self, data):
    lib.host_checkin(config, data)


#
# API routes
#
class API_Root(Resource):
    def get(self):
        """
        Return basic details of the API
        ---
        tags:
          - root
        responses:
          200:
            description: OK
            schema:
              type: object
              id: Message
              properties:
                message:
                  type: string
                  description: A text message describing the result
                  example: "The foo was successfully maxed"
        """
        return {"message": "pvcbootstrapd API"}, 200


api.add_resource(API_Root, "/")


class API_Checkin(Resource):
    def get(self):
        """
        Return checkin details of the API
        ---
        tags:
          - checkin
        responses:
          200:
            description: OK
            schema:
              type: object
              id: Message
        """
        return {"message": "pvcbootstrapd API Checkin interface"}, 200


api.add_resource(API_Checkin, "/checkin")


class API_Checkin_DNSMasq(Resource):
    def post(self):
        """
        Register a checkin from the DNSMasq subsystem
        ---
        tags:
          - checkin
        consumes:
          - application/json
        parameters:
          - in: body
            name: dnsmasq_checkin_event
            description: An event checkin from an external bootstrap tool component.
            schema:
              type: object
              required:
                - action
              properties:
                action:
                  type: string
                  description: The action of the event.
                  example: "add"
                macaddr:
                  type: string
                  description: (add, old) The MAC address from a DHCP request.
                  example: "ff:ff:ff:ab:cd:ef"
                ipaddr:
                  type: string
                  description: (add, old) The IP address from a DHCP request.
                  example: "10.199.199.10"
                hostname:
                  type: string
                  description: (add, old) The client hostname from a DHCP request.
                  example: "pvc-installer-live"
                client_id:
                  type: string
                  description: (add, old) The client ID from a DHCP request.
                  example: "01:ff:ff:ff:ab:cd:ef"
                vendor_class:
                  type: string
                  description: (add, old) The DHCP vendor-class option from a DHCP request.
                  example: "CPQRIB3 (HP Proliant DL360 G6 iLO)"
                user_class:
                  type: string
                  description: (add, old) The DHCP user-class option from a DHCP request.
                  example: None
        responses:
          200:
            description: OK
            schema:
              type: object
              id: Message
        """
        try:
            data = json.loads(flask.request.data)
        except Exception as e:
            logger.warn(e)
            data = {"action": None}
        logger.info(f"Handling DNSMasq checkin for: {data}")

        task = dnsmasq_checkin.delay(data)
        logger.debug(task)
        return {"message": "received checkin from DNSMasq"}, 200


api.add_resource(API_Checkin_DNSMasq, "/checkin/dnsmasq")


class API_Checkin_Host(Resource):
    def post(self):
        """
        Register a checkin from the Host subsystem
        ---
        tags:
          - checkin
        consumes:
          - application/json
        parameters:
          - in: body
            name: host_checkin_event
            description: An event checkin from an external bootstrap tool component.
            schema:
              type: object
              required:
                - action
              properties:
                action:
                  type: string
                  description: The action of the event.
                  example: "begin"
                hostname:
                  type: string
                  description: The system hostname.
                  example: "hv1.mydomain.tld"
                host_macaddr:
                  type: string
                  description: The MAC address of the system provisioning interface.
                  example: "ff:ff:ff:ab:cd:ef"
                host_ipaddr:
                  type: string
                  description: The IP address of the system provisioning interface.
                  example: "10.199.199.11"
                bmc_macaddr:
                  type: string
                  description: The MAC address of the system BMC interface.
                  example: "ff:ff:ff:01:23:45"
                bmc_ipaddr:
                  type: string
                  description: The IP addres of the system BMC interface.
                  example: "10.199.199.10"
        responses:
          200:
            description: OK
            schema:
              type: object
              id: Message
        """
        try:
            data = json.loads(flask.request.data)
        except Exception as e:
            logger.warning(f"Invalid JSON data, setting action to None: {e}")
            data = {"action": None}
        logger.info(f"Handling Host checkin for: {data}")

        task = host_checkin.delay(data)
        logger.debug(task)
        return {"message": "received checkin from Host"}, 200


api.add_resource(API_Checkin_Host, "/checkin/host")
