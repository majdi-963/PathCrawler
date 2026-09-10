# Results

The expected result is a functional command-line tool that can enumerate paths on a local demo server and produce terminal, JSON, and CSV output.

Example demonstration workflow:

```bash
cd examples/demo_server
python -m http.server 8000
```

From another terminal in the project root:

```bash
python main.py scan --url http://127.0.0.1:8000 --wordlist wordlists/common.txt -o reports/demo.json
```

Expected example findings include `/admin`, `/login`, and `/secret.txt` because those paths are intentionally included in the local demo environment.

Any timing, request count, or response size values shown in the README are examples. Actual measurements depend on the machine, Python version, operating system, and server behavior.
