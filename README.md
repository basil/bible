# Orthodox Liturgical English Bible (OLEB)

The Orthodox Liturgical English Bible joins Brenton’s English Septuagint, with selected readings from Codex Alexandrinus, to the King James New Testament conformed to Robinson and Pierpont’s Byzantine text (2026). It includes the deuterocanonical books and revises vocabulary, spelling, grammar, and punctuation while retaining traditional English. The edition is available as a single-volume PDF and an online reader; [the introduction](https://oleb.bible/read/introduction) explains its texts, editorial choices, and conventions.

**[Read online](https://oleb.bible/read/) · [Download the PDF](https://oleb.bible/bible.pdf)**

## Build

Install Docker with the Compose plugin and Make, and allow about 5 GB of disk space:

```sh
make bootstrap  # build the tool image; needs the network
make pdf        # prepare, fill, check, and write dist/bible.pdf
```

A cold filled build can take an hour or more. [AGENTS.md](AGENTS.md) covers the other build targets and checks; [CONTRIBUTING.md](CONTRIBUTING.md) explains how to change the edition. The [source catalogue](sources/README.md) records the pinned inputs and their notices. Maintainer guides in [docs/](docs/) describe the implementation and are not published on the reader’s website.

## License

Copyright © 2026 Basil Crow. Basil Crow’s original editorial material and the assembled edition, to the extent copyright protects them, are licensed under [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/). This applies only to his rights; source translations and other third-party materials retain their own public-domain status, licenses, and permissions. Build scripts, configuration, and development documentation are under the [MIT License](LICENSE).
