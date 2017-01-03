$ mkdir opencv_contrib
cmake -D CMAKE_BUILD_TYPE=RELEASE \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D OPENCV_EXTRA_MODULES_PATH=$HOME/code/opencv_contrib/modules \
    -D PYTHON_LIBRARY=$HOME/.pyenv/versions/3.5.2/Python.framework/Versions/3.5/lib/libpython3.5m.dylib \
    -D PYTHON_INCLUDE_DIR=$HOME/.pyenv/versions/3.5.2/Python.framework/Versions/3.5/include/python3.5m \
    -D PYTHON3_EXECUTABLE=$HOME/.pyenv/versions/3.5.2/bin/python \
    -D PYTHON3_PACKAGES_PATH=$HOME/.pyenv/versions/3.5.2/lib/python3.5/site-packages \
    -D BUILD_opencv_python2=OFF \
    -D BUILD_opencv_python3=ON \
    -D INSTALL_PYTHON_EXAMPLES=ON \
    -D INSTALL_C_EXAMPLES=OFF \
    -D BUILD_EXAMPLES=ON ..

