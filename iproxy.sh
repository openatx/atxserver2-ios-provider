#!/bin/bash
#

if test $# != 3
then
    echo "Usage: iproxy.sh LOCAL_PORT REMOTE_PORT UDID"
    exit 1
fi

LOCAL_PORT=$1
REMOTE_PORT=$2
UDID=$3

while true
do
	./node_modules/.bin/irelay --udid $UDID $REMOTE_PORT:$LOCAL_PORT
done
