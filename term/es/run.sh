#$ docker run -d -v "$PWD/config":/usr/share/elasticsearch/config elasticsearch
#$ docker run -d -v "$PWD/esdata":/usr/share/elasticsearch/data elasticsearch
docker run -a STDOUT -v "$PWD/config":/usr/share/elasticsearch/config -v "$PWD/esdata":/usr/share/elasticsearch/data -P elasticsearch:2
