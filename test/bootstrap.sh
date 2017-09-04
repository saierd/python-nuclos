#!/bin/bash

# TODO: Download nuclos.sh from Github instead of copying it from the test directory.
cp python-nuclos/test/nuclos.sh .

./nuclos.sh install postgres
./nuclos.sh install 4.17.5

./nuclos.sh import python-nuclos/test/test.nuclet
