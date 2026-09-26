FROM ubuntu:26.04
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        fontconfig \
        fontforge \
        fonts-sil-ezra \
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
        unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
COPY dependencies.json /opt/dependencies.json
COPY requirements.txt /opt/requirements.txt
COPY scripts/install-upstream.py /opt/install-upstream.py
COPY config/ptxprint-allow-otf.patch /opt/ptxprint-allow-otf.patch
COPY sources/GFS_Didot.zip /opt/GFS_Didot.zip
COPY sources/OTF-source-code-pro-2.042R-u_1.062R-i.zip /opt/OTF-source-code-pro.zip
COPY sources/erewhon.zip /opt/erewhon.zip
RUN python3 /opt/install-upstream.py \
    && mkdir -p /usr/local/share/fonts/adobe \
    && mkdir -p /usr/local/share/fonts/erewhon \
    && mkdir -p /usr/local/share/fonts/gfs \
    && cd /opt/utopia \
    && ./build.sh \
    && cp dist/*.otf /usr/local/share/fonts/adobe/ \
    && unzip -j /opt/GFS_Didot.zip 'GFSDidot*.otf' -d /usr/local/share/fonts/gfs/ \
    && chmod 644 /usr/local/share/fonts/gfs/*.otf \
    && unzip -j /opt/OTF-source-code-pro.zip 'OTF/*.otf' -d /usr/local/share/fonts/adobe/ \
    && unzip -j /opt/erewhon.zip 'erewhon/opentype/*.otf' -d /usr/local/share/fonts/erewhon/ \
    && chmod 644 /usr/local/share/fonts/adobe/*.otf /usr/local/share/fonts/erewhon/*.otf \
    && fc-cache -f \
    && fc-list \
    && dpkg-query -W >/opt/os-packages.tsv
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /work
