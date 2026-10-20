# Contributing

Thanks for improving remote-rsync-size.

1. Open an issue describing bugs or desired improvements before making major changes.
2. Create a feature branch and keep pull requests focused.
3. Install the development dependencies with `pip install -e '.[dev]'`.
4. Add or update tests and run `python -m pytest -q` before submitting.
5. Avoid adding external services or remote-server requirements to the unit tests.

Please do not commit credentials, private keys, `known_hosts` files containing
sensitive internal infrastructure names, or actual customer filesystem listings.
