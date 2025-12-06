#!/bin/bash

exec python3 analyser.py -i can1 --canid-map can_names.csv \
         --filter 0E602380~1FFFFFFF \
         --filter 02040580~1FFFFFFF \
         --filter 02040588~1FFFFFFF \
         --filter 02060580~1FFFFFFF \
         --filter 02060588~1FFFFFFF \
         --filter 0E642380~1FFFFFFF \
         --filter 0E642380~1FFFFFFF \
         --filter 0E662380~1FFFFFFF \
         --filter 02040B88~1FFFFFFF \
         --filter 02060B88~1FFFFFFF \
         --filter 0E622380~1FFFFFFF