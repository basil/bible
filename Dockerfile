FROM ubuntu:resolute
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
        python3-venv \
        qpdf \
        texlive-xetex \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && dpkg-query -W >/opt/os-packages.tsv
# Layers from the least to the most often changed.
COPY requirements.txt /opt/requirements.txt
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --only-binary=:all: \
        -r /opt/requirements.txt
COPY dependencies.json scripts/install-upstream.py /opt/
# .dockerignore admits only the font archives.
COPY sources/*.zip /opt/sources/
RUN python3 /opt/install-upstream.py \
    && cd /opt/utopia \
    && ./build.sh \
    && mkdir /usr/local/share/fonts/utopia \
    && cp dist/*.otf /usr/local/share/fonts/utopia/ \
    && fc-cache -f \
    && fc-list
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /work
