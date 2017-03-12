#!/bin/sh
docker build -t pokereval .
docker run --name pokereval -it -p 5000:5000 -v $PWD:/opt/pe pokereval python /opt/pe/app.py
