# Project Idea

PathCrawler is a command-line cybersecurity tool that tests whether common web paths are reachable on a target site. A user supplies a target base URL and a wordlist. The tool generates normalized candidate paths, performs HTTP GET requests, and records response metadata such as status code, content length, content type, redirect target, response time, and classification.

The project demonstrates standard web reconnaissance concepts in an educational and controlled way. It uses only Python's standard library, making it easy to inspect, run, and explain during a university project defense.

The included local demo server allows students to demonstrate the tool safely without scanning external systems.
