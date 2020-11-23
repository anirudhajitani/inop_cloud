#!/bin/bash

export LOAD=0.5
while true
do 
	yes > /dev/null & export PID=$!
	sleep $LOAD
     	kill -9 $PID
     	#sleep `echo "1 - $LOAD" | bc`
done
