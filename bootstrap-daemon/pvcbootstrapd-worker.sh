#!/usr/bin/env bash

# pvcbootstrapd-worker.py - API Celery worker daemon startup stub
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

CELERY_BIN="$( which celery )"

# This absolute hackery is needed because Celery got the bright idea to change how their
# app arguments work in a non-backwards-compatible way with Celery 5.
case "$( cat /etc/debian_version )" in
    10.*)
        CELERY_ARGS="worker --app pvcbootstrapd.flaskapi.celery --concurrency 99 --pool gevent --loglevel DEBUG"
    ;;
    *)
        CELERY_ARGS="--app pvcbootstrapd.flaskapi.celery worker --concurrency 99 --pool gevent --loglevel DEBUG"
    ;;
esac

${CELERY_BIN} ${CELERY_ARGS}
exit $?
