#!/bin/sh
# Collect the host's Valkyrie OT faces into build/valkyrie, named by their
# PostScript names whatever their files are called, for the image build to
# assemble OLEBFont from (scripts/build_olebfont.py); the directory is left
# empty where the host has none, and the image is then built from Utopia.
set -eu

mkdir -p build/valkyrie
rm -f build/valkyrie/*.otf
# make bootstrap WITHOUT_VALKYRIE=1 builds the image a pull request gets.
if [ -n "${WITHOUT_VALKYRIE:-}" ]; then
	exit 0
fi
if ! command -v fc-list >/dev/null 2>&1; then
	echo 'fontconfig is unavailable; building without Valkyrie.' >&2
	exit 0
fi

# Keep discovery outside the pipeline so its failure stops bootstrap.
fonts=$(fc-list ':family=Valkyrie OT A' --format='%{postscriptname}\t%{file}\n')
printf '%s\n' "$fonts" | while IFS="$(printf '\t')" read -r name font; do
	case "$name" in
	ValkyrieOTARegular | ValkyrieOTAItalic | ValkyrieOTABold | ValkyrieOTABoldItalic)
		target="build/valkyrie/$name.otf"
		# The assembly reads OpenType CFF faces, not a web or TrueType copy.
		case "$font" in
		*.otf | *.OTF) ;;
		*)
			echo "Skipping $font: not an OpenType (.otf) face" >&2
			continue
			;;
		esac
		# Two installed copies that differ would leave the image to chance.
		if [ -e "$target" ] && ! cmp -s "$font" "$target"; then
			echo "Two different Valkyrie faces named $name; remove one: $font" >&2
			exit 1
		fi
		cp "$font" "$target"
		# The tests read the image's copy as the invoking user, not as root,
		# and a font archive may keep owner-only permissions.
		chmod 644 "$target"
		;;
	'') ;;
	*)
		echo "Unexpected Valkyrie face: $name ($font)" >&2
		exit 1
		;;
	esac
done
