FROM ubuntu:26.04
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        fontconfig \
        fonts-sil-ezra \
        fonts-sil-gentiumplus \
        gir1.2-gtk-3.0 \
        git \
        poppler-utils \
        python3 \
        python3-cairo \
        python3-gi \
        python3-pip \
        python3-setuptools \
        python3-venv \
        python3-wheel \
        qpdf \
        texlive-xetex \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY dependencies.json /opt/dependencies.json
COPY requirements.txt /opt/requirements.txt
COPY scripts/install-upstream.py /opt/install-upstream.py
RUN python3 /opt/install-upstream.py \
    && mkdir -p /usr/local/share/fonts/ptxprint \
    && cp /opt/ptxprint/fonts/*.ttf /usr/local/share/fonts/ptxprint/ \
    && fc-cache -f \
    && dpkg-query -W >/opt/os-packages.tsv
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1788220800
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /work
ENTRYPOINT ["python3", "scripts/pipeline.py"]