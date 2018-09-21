#!/bin/sh
apt-get install git make gcc python-dev wget -y

cd /tmp
# wget http://download.gna.org/pokersource/sources/poker-eval-138.0.tar.gz
wget http://http.debian.net/debian/pool/main/p/poker-eval/poker-eval_138.0.orig.tar.gz
# mv poker-eval_138.0.orig.tar.gz poker-eval_138.0.tar.gz
tar -xvf poker-eval_138.0.orig.tar.gz
cd poker-eval-138.0
./configure
make
make install
ldconfig # this is important

cd /tmp
git clone https://github.com/minmax/pypoker-eval
cd pypoker-eval/
export C_INCLUDE_PATH=/usr/local/include/poker-eval
export LIBRARY_PATH=/usr/local/lib
python setup.py install
cp pokereval.py /usr/local/lib/python2.7/dist-packages/
