# Testing

The project uses `unittest`, which is included in Python's standard library. Tests are stored in the `tests/` directory and can be run with:

```bash
python -m unittest discover
```

The tests cover:

- Wordlist loading.
- Comment and blank-line handling.
- Duplicate removal.
- URL and path construction.
- Configuration loading and validation.
- Status filtering.
- False-positive baseline logic.
- Basic scanner behavior with a local HTTP server.
- Error handling for missing wordlists and invalid configuration.

No third-party testing framework is required.
