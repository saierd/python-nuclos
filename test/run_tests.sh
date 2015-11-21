#!/bin/bash

vagrant up

python3 test.py

vagrant halt
