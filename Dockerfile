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
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && dpkg-query -W >/opt/os-packages.tsv
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
754a2e3ebb945ae905d720ac5896b3b34acc9546dd6551ef9536869788629dae  OTF-source-code-pro-2.042R-u_1.062R-i.zip
865ed6e5b4aeda1b5a350a2dc5d4b239f515059812366acc6dcd04c80fd9d942  erewhon.zip
afd722e515f0c94e08902c8960f8799736657d98348cb00068d827e71bbbb706  erewhon-math.zip
SUMS
fonts=/usr/local/share/fonts
unzip -qj GFS_Didot.zip 'GFSDidot*.otf' -d $fonts/gfs_didot
unzip -qj OTF-source-code-pro-2.042R-u_1.062R-i.zip 'OTF/*.otf' -d $fonts/source_code_pro
# unzip keeps each archive's permissions, ignoring the umask: GFS Didot's
# are owner-only.
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
ARG USFMTC_COMMIT=f1e4f23e83953032c0a9574a1df9ab4b4ec89a22
# renovate: datasource=git-tags depName=ptxprint
ARG PTXPRINT_URL=https://github.com/sillsdev/ptx2pdf.git
ARG PTXPRINT_TAG=3.1.2
ARG PTXPRINT_COMMIT=2b10e5a7dc984ee2be836ecd5d07253c77ada0b1
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
# Two fixes to how PTXprint moves the notes of a crowded margin apart. It
# orders notes by their tops and then puts the shorter first, so notes on one
# line of text can print out of the text's order: keep its stable sort to the
# tops alone. And when it lifts a block of notes, it checks the note above the
# block against the top of the page, or none, and can lift the block off the
# page. Each grep fails the build if an upgrade has rewritten the line.
notes=/opt/ptxprint/python/lib/ptxprint/marginnotes.py
grep -qF 't.sort(key=lambda n:(-n.ymax, -n.ymin))' $notes
grep -qx '                            start = k' $notes
sed -i -e 's/t\.sort(key=lambda n:(-n\.ymax, -n\.ymin))/t.sort(key=lambda n: -n.ymax)/' \
    -e 's/^\( *start = k\)$/\1 + 1/' $notes
cd /opt/utopia
./build.sh
# The venv already holds requirements.txt. PTXprint's metadata names usfmtc's
# moving main branch, not the pinned commit, so neither brings dependencies.
/opt/venv/bin/pip install --no-cache-dir --no-deps --no-build-isolation \
    /opt/usfmtc /opt/ptxprint
EOF

# Font assembly changes should not refetch upstream projects or Python wheels.
COPY scripts/ /opt/scripts/
RUN /opt/venv/bin/python /opt/scripts/patch_margin_convergence.py \
    /opt/ptxprint/python/lib/ptxprint \
    && /opt/venv/bin/python -c 'import ptxprint; from pathlib import Path; import sys; sys.path.insert(0, "/opt/scripts"); from patch_margin_convergence import patch; patch(Path(ptxprint.__file__).parent)'
RUN /opt/venv/bin/python /opt/scripts/patch_nested_styles.py
RUN <<EOF
set -eu
# Assemble the normalized text family with separate source hint dictionaries.
/opt/venv/bin/python /opt/scripts/build_olebfont.py \
    --utopia /opt/utopia --erewhon /opt/sources/erewhon.zip \
    --erewhon-math /opt/sources/erewhon-math.zip \
    --output /usr/local/share/fonts/olebfont
chmod 644 /usr/local/share/fonts/olebfont/*
fc-cache -f
fc-list
EOF

ENV LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /work
# The pipeline compares this copy with the checkout to refuse a stale image.
COPY Dockerfile /opt/Dockerfile
