# Security Policy

## Supported Versions

The following versions of prefixopt currently receive security updates:

| Version | Supported          |
|---------|--------------------|
| latest  |  Yes               |
| older   |  No                |

We recommend always using the latest available version.

---

## Scope

This security policy applies to the **prefixopt** core library, CLI, and GUI.

The following are **out of scope**:

- Vulnerabilities in third-party dependencies (report them to the respective
  maintainers).
- Issues in Python itself or in PySide6.
- Bugs that do not have a security impact (use the standard
  [issue tracker](../../issues) instead).

---

## Reporting a Vulnerability

If You discover a security vulnerability in prefixopt, **please do not open
a public issue**.

Instead, report it privately through one of the following channels:

- **GitHub Private Security Advisory**:
  [Report a vulnerability](../../security/advisories/new)
- **Direct contact**: open a private communication with the maintainer
  through GitHub.

Please include the following in Your report:

- A clear description of the vulnerability.
- Steps to reproduce the issue.
- The potential impact (what an attacker could achieve).
- Your suggested fix, if any.

---

## Response Process

After receiving a report, we will:

1. Acknowledge receipt within **72 hours**.
2. Investigate and assess the severity.
3. Develop and test a fix.
4. Release a patched version.
5. Credit the reporter in the release notes, if desired.

We ask that You give us a reasonable amount of time to address the issue
before any public disclosure.

---

## Known Risk Areas

prefixopt processes user-supplied input such as IP prefix lists, text files,
and configuration data. The following areas are considered sensitive:

- **File reading**: large or malformed files could cause excessive memory
  consumption. Hard limits are implemented, but edge cases may exist.
- **Input parsing**: the parser handles arbitrary text formats. Malformed
  input should be rejected gracefully, not cause crashes.
- **GUI file dialogs**: file paths supplied by the user are passed to the
  core library. Path traversal is not applicable, but unexpected file types
  should be handled safely.

---

## Attribution

We are grateful to researchers and users who responsibly disclose security
issues. Contributors who report valid vulnerabilities will be acknowledged
in the project changelog.
