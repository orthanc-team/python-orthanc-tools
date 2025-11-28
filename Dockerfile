FROM python:3.14

RUN python -m pip install -U setuptools wheel build

WORKDIR /src

COPY . /src/

RUN python -m build .
RUN pip install dist/orthanc_tools*.tar.gz

WORKDIR /