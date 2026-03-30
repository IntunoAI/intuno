# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | Yes                |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly. **Do not open a public GitHub issue.**

Email security reports to: **security@intuno.net**

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge your report within 48 hours and aim to provide a fix or mitigation plan within 7 days.

## Security Features

Intuno includes several security measures:

- **JWT authentication** with configurable expiration
- **Bcrypt password hashing** for user accounts
- **Per-agent credential encryption** using Fernet symmetric encryption (see `src/core/credential_crypto.py`)
- **SSRF protection** on agent invoke endpoints — private IP ranges are blocked by default (see `src/core/url_validation.py`)
- **API key hashing** — API keys are stored as bcrypt hashes, never in plaintext

## Production Deployment Checklist

- Set a strong, unique `JWT_SECRET_KEY` (do not use the development default)
- Set `ENVIRONMENT=production`
- Restrict `CORS_ORIGINS` to your actual frontend domains
- Set `CREDENTIALS_ENCRYPTION_KEY` to a dedicated secret (separate from JWT)
- Use TLS termination in front of the application
- Restrict database access to the application server only
