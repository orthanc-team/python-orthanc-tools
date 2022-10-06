FROM python:3.10

RUN python -m pip install -U setuptools wheel build

RUN mkdir /src

COPY orthanc_tools/ /src/orthanc_tools/
COPY LICENSE.txt /src
COPY MANIFEST.in /src
COPY pyproject.toml /src
COPY README.md /src
COPY setup.cfg /src
COPY setup.py /src
COPY tox.ini /src

WORKDIR /src

RUN python -m build .
RUN pip install dist/orthanc_tools*.tar.gz

WORKDIR /