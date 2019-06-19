#!/bin/bash
#

for UDID in $(idevice_id -l)
do
	NAME=$(idevicename -u $UDID)
	echo "$UDID: $NAME"
done
