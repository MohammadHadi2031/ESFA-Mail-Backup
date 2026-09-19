# Security Policy

## Supported versions

The latest released version is the only one that receives fixes.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Report it through GitHub's private vulnerability reporting (the **Security** tab → **Report a vulnerability**), or by email to the address listed on the repository owner's profile.

Please include:

- the version or commit you tested,
- what an attacker could achieve,
- and the steps to reproduce it.

You can expect an acknowledgement within a few days and an assessment of whether a fix is needed.

## Scope

This application runs locally on a single Windows machine. Findings that are in scope include, for example:

- anything that exposes stored IMAP credentials outside the current Windows user account,
- the local UI being reachable from outside `127.0.0.1`,
- TLS validation being weakened or bypassed on the IMAP connection,
- writing outside `%LOCALAPPDATA%\EsfaMailBackup` and the user-selected backup folder,
- path traversal through attacker-controlled IMAP folder names.

Out of scope: an attacker who already has administrative access to the machine, or who is logged in as the same Windows user — Windows DPAPI is designed to protect against neither.
