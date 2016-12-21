docker run -it --link es_elasticsearch_master_1:es_host -v "$PWD:/code" -P pe python /code/main.py
