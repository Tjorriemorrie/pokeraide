FROM python:3.6.6

RUN mkdir -p /opt/pe
RUN pip install --upgrade pip
RUN pip install --upgrade sanic
EXPOSE 5657

ADD install_pokereval.sh /tmp/install_pokereval.sh
RUN bash /tmp/install_pokereval.sh
