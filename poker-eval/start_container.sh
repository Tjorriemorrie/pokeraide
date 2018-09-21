#!/bin/sh
docker build -t spokereval .
docker run --name spokereval -it -p 5657:5657 -v $PWD:/opt/pe spokereval python /opt/pe/app_sanic.py
