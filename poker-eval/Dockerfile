FROM python:latest

RUN mkdir -p /opt/pe
RUN pip install flask
EXPOSE 5000

ADD install_pokereval.sh /tmp/install_pokereval.sh
RUN bash /tmp/install_pokereval.sh

