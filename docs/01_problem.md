# Problem Statement

Modern web applications often contain more reachable paths than their public navigation reveals. Administrative folders, backup files, test routes, static assets, and old deployment artifacts may remain accessible after development or maintenance work. These exposed paths can disclose information or reveal weak access controls.

Security teams need a safe and repeatable way to enumerate visible HTTP paths during authorized assessments. Manual checking is slow, inconsistent, and easy to document poorly. PathCrawler addresses this problem by automating path enumeration with a supplied wordlist while staying within a narrow defensive scope.

The project does not attempt exploitation, authentication bypass, password guessing, payload execution, or vulnerability exploitation. It focuses only on HTTP path discovery and response classification.
