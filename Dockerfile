FROM ubuntu:resolute
# Ubuntu packages follow the LTS repositories.
# hadolint ignore=DL3008
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates \
        fontconfig \
        fontforge \
        fonts-sil-ezra \
        gir1.2-gtk-3.0 \
        git \
        libharfbuzz-bin \
        poppler-utils \
        python3 \
        python3-cairo \
        python3-gi \
        python3-venv \
        qpdf \
        texlive-xetex \
        unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
# Layers from the least to the most often changed.
# PTXprint's fontconfig template rejects OpenType files, but it includes the
# system configuration, where an acceptfont rule takes precedence.
COPY <<EOF /etc/fonts/conf.d/99-accept-local-fonts.conf
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <selectfont>
    <acceptfont>
      <glob>/usr/local/share/fonts/*</glob>
    </acceptfont>
  </selectfont>
</fontconfig>
EOF

# The font archives are committed as downloaded; sources/README.md says
# where each came from. .dockerignore admits only the font archives.
COPY sources/*.zip /opt/sources/
WORKDIR /opt/sources
RUN <<EOF
set -eu
# --strict: a malformed line would otherwise be skipped with only a warning.
sha256sum --strict -c <<SUMS
866855b0296579451c233fc78bec82918996a8df7341ee2f1c09d7bc94440680  GFS_Didot.zip
9d02c294c33aad58de44c408d20f5a7b06aefad411bce9f2e096a4040900f702  GFS_Heraklit.zip
754a2e3ebb945ae905d720ac5896b3b34acc9546dd6551ef9536869788629dae  OTF-source-code-pro-2.042R-u_1.062R-i.zip
865ed6e5b4aeda1b5a350a2dc5d4b239f515059812366acc6dcd04c80fd9d942  erewhon.zip
afd722e515f0c94e08902c8960f8799736657d98348cb00068d827e71bbbb706  erewhon-math.zip
a5705119752a634a4db511a198fb1de4b876da1b07a7f49e0e3443939750fb55  newpx.zip
SUMS
# The Greek faces are installed with OLEBFont below, by the base it was built from.
fonts=/usr/local/share/fonts
unzip -qj OTF-source-code-pro-2.042R-u_1.062R-i.zip 'OTF/*.otf' -d $fonts/source_code_pro
# unzip keeps each archive's permissions, ignoring the umask.
chmod 644 $fonts/*/*.otf
EOF

COPY requirements.txt /opt/requirements.txt
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --only-binary=:all: \
        -r /opt/requirements.txt
# Upstream projects, pinned by commit; Renovate follows the tag or branch
# beside each. Network is permitted only while building this image.
# renovate: datasource=git-refs depName=utopia
ARG UTOPIA_URL=https://github.com/basil/adobe-utopia-type1.git
ARG UTOPIA_BRANCH=master
ARG UTOPIA_COMMIT=75db04f06d90e6dd3227de88b76f8bfea88f8785
# renovate: datasource=git-refs depName=usfmtc
ARG USFMTC_URL=https://github.com/usfm-bible/usfmtc.git
ARG USFMTC_BRANCH=main
ARG USFMTC_COMMIT=81a0bc761571169843b74c52c548f72cbc73a8d7
# renovate: datasource=git-tags depName=ptxprint
ARG PTXPRINT_URL=https://github.com/sillsdev/ptx2pdf.git
ARG PTXPRINT_TAG=3.1.3
ARG PTXPRINT_COMMIT=756cdc265ba5aca816bcca87168399fbebb4c20a
# Fetching and building several projects in one layer requires their directories.
# hadolint ignore=DL3003
RUN <<EOF
set -eu
fetch() {
    git init -q "/opt/$1"
    git -C "/opt/$1" fetch -q --depth 1 "$2" "$3"
    git -C "/opt/$1" checkout -q --detach FETCH_HEAD
    # A tag object's hash would check out the tagged commit instead.
    if [ "$(git -C "/opt/$1" rev-parse HEAD)" != "$3" ]; then
        echo "$1: $3 is not a commit" >&2
        exit 1
    fi
}
fetch utopia "$UTOPIA_URL" "$UTOPIA_COMMIT"
fetch usfmtc "$USFMTC_URL" "$USFMTC_COMMIT"
fetch ptxprint "$PTXPRINT_URL" "$PTXPRINT_COMMIT"
cd /opt/utopia
./build.sh
# The venv already holds requirements.txt. PTXprint's metadata names usfmtc's
# moving main branch, not the pinned commit, so neither brings dependencies.
/opt/venv/bin/pip install --no-cache-dir --no-deps --no-build-isolation \
    /opt/usfmtc /opt/ptxprint
EOF

# The host's Valkyrie OT faces, which make bootstrap collects into build/valkyrie
# (an empty directory where the host has none). Valkyrie is proprietary and
# never committed; the edition is then set in Utopia.
COPY build/valkyrie/ /opt/valkyrie/
# Font assembly changes should not refetch upstream projects or Python wheels.
COPY scripts/ /opt/scripts/
RUN /opt/venv/bin/python /opt/scripts/patch_margin_convergence.py \
    && /opt/venv/bin/python /opt/scripts/patch_emitter_prefix.py \
    && /opt/venv/bin/python /opt/scripts/patch_periph.py
RUN <<EOF
set -eu
# Assemble OLEBFont from Valkyrie OT where the host provided it, else from
# Utopia, and install the Greek face paired with it (fonts/olebfont, fonts/greek).
/opt/venv/bin/python /opt/scripts/build_olebfont.py \
    --utopia /opt/utopia --valkyrie /opt/valkyrie \
    --erewhon /opt/sources/erewhon.zip \
    --erewhon-math /opt/sources/erewhon-math.zip \
    --newpx /opt/sources/newpx.zip \
    --gfs-didot /opt/sources/GFS_Didot.zip \
    --gfs-heraklit /opt/sources/GFS_Heraklit.zip \
    --output /usr/local/share/fonts
chmod 644 /usr/local/share/fonts/olebfont/* /usr/local/share/fonts/greek/*
fc-cache -f
fc-list
EOF

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /work
# The pipeline compares this copy with the checkout to refuse a stale image.
COPY Dockerfile /opt/Dockerfile
