#!/bin/bash

export LOAD=$1
echo $LOAD
count=0
for (( ; ; ))
do
	count=$((count+1))
	if [ $count -ge 100 ]
	then	
		sleep 0.001
		count=0
	fi
	echo "" > /dev/null 
	continue
done
