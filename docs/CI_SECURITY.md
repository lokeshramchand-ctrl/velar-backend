# CI/CD Security Scanning

This document describes the comprehensive security scanning pipeline configured for Velar backend.

## Overview

The CI/CD pipeline implements multiple layers of security scanning to catch vulnerabilities before they reach production:

1. **Secret Scanning** - Detects accidentally committed credentials
2. **Static Analysis (SAST)** - Identifies code vulnerabilities
3. **Dependency Scanning** - Finds vulnerable libraries and components
4. **Container Scanning** - Checks Docker images for vulnerabilities
5. **Infrastructure as Code Scanning** - Validates deployment configurations

## Scanning Tools

### Secret Scanning

#### Gitleaks (Per-Commit)
- **Location:** `.github/workflows/ci.yml`
- **Trigger:** Every push and pull request
- **Configuration:** Uses GitHub Actions default config
- **Coverage:** Detects API keys, OAuth tokens, database URIs, AWS credentials

**Configuration in CI:**
```yaml
- name: Run gitleaks
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

#### TruffleHog (Deep Scan)
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Daily schedule + push to main
- **Coverage:** More aggressive regex patterns for hidden secrets
- **Output:** JSON report uploaded as artifact

**Running locally:**
```bash
pip install truffleHog
trufflehog filesystem . --json
```

#### Pre-commit Hooks (Local Prevention)
- **Location:** `.pre-commit-config.yaml`
- **Tools:** gitleaks + detect-private-key
- **Enforcement:** Blocks commits with detected secrets

### Static Application Security Testing (SAST)

#### CodeQL
- **Language:** Python (extensible to JavaScript if frontend included)
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Push to main/master, pull requests, daily schedule
- **Coverage:**
  - SQL injection
  - Path traversal
  - Cross-site scripting (XSS)
  - Authentication bypass
  - Hardcoded credentials
  - Command injection

**SARIF Results:**
Findings appear in GitHub Security tab under "Code scanning alerts"

**Running locally:**
```bash
codeql database create codeql-db --language=python
codeql database analyze codeql-db --format=sarif-latest --output=results.sarif
```

#### Semgrep
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Push, pull request, daily schedule
- **Configuration:** `p/security-audit` ruleset
- **Coverage:**
  - OWASP Top 10
  - CWE-ranked vulnerabilities
  - Python/Django security patterns

**Running locally:**
```bash
pip install semgrep
semgrep --config p/security-audit .
```

#### Bandit
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Every security scan workflow
- **Coverage:**
  - Insecure cryptography
  - SQL injection vulnerabilities
  - Command execution risks
  - Hardcoded secrets
  - Unsafe imports

**Running locally:**
```bash
pip install bandit
bandit -r . -f json -o bandit-report.json
```

### Dependency Vulnerability Scanning

#### pip-audit (Production)
- **Location:** `.github/workflows/ci.yml`
- **Trigger:** Every commit
- **Dependencies:** `requirements.txt`
- **Action:** **BLOCKS** merge if vulnerabilities found

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

#### Safety
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Daily schedule + push to main
- **Database:** CVE/security advisory database
- **Coverage:** Known vulnerabilities in PyPI packages

```bash
pip install safety
safety check -r requirements.txt --json
```

#### Snyk (Optional - requires token)
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Daily schedule + push to main
- **Coverage:** Broader vulnerability database + license scanning
- **Setup:** Add `SNYK_TOKEN` to GitHub Secrets

```bash
npm install -g snyk
snyk auth YOUR_TOKEN
snyk test
```

#### OWASP Dependency Check
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Daily schedule + push to main
- **Coverage:**
  - Known published vulnerabilities
  - Experimental analyzers for indirect dependencies

### Container Image Scanning

#### Trivy
- **Location:** `.github/workflows/security-scanning.yml`
- **Trigger:** Push to main, daily schedule
- **Image:** Scans built Docker image from `Dockerfile`
- **Coverage:**
  - OS package vulnerabilities (Alpine, Debian, etc.)
  - Python package vulnerabilities
  - Misconfigurations (running as root, outdated base images)

**Running locally:**
```bash
docker build -t velar:scan .
trivy image velar:scan --severity HIGH,CRITICAL
```

**Trivy Configuration in workflow:**
```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: velar:scan
    format: "sarif"
    severity: "CRITICAL,HIGH,MEDIUM"
```

#### Hadolint (Dockerfile Linting)
- **Location:** `.github/workflows/ci.yml`
- **Coverage:**
  - Best practices (use specific base image versions)
  - Security issues (running as root, missing HEALTHCHECK)
  - Efficiency (layer optimization)

```bash
docker run --rm -i hadolint/hadolint < Dockerfile
```

## Dependency Updates

### Dependabot
- **Location:** `.github/dependabot.yml`
- **Configuration:**
  - **pip:** Weekly updates on Mondays
  - **github-actions:** Weekly updates
  - **docker:** Weekly base image updates
- **PR Limit:** Max 10 open dependency PRs
- **Auto-rebase:** Enabled for cleaner history
- **Commit prefix:** `chore(deps):` for pip, `ci(actions):` for GH actions

**Dependabot behavior:**
- Creates PRs for new versions
- Auto-assigns to `lokeshramchand-ctrl`
- Security updates get priority and bypass rate limiting
- Uses squash-and-rebase strategy

### Enabling GitHub Secret Scanning
GitHub automatically scans public repos, but enable for private repos:
1. Go to Settings → Security → Secret scanning
2. Enable "Secret Scanning" and "Secret scanning push protection"

## Security Scanning Workflows

### `.github/workflows/ci.yml` (Every commit)
- ✅ Gitleaks secret scanning
- ✅ Ruff linting (includes bandit security rules)
- ✅ pip-audit dependency scanning (BLOCKS on findings)
- ✅ Pytest unit tests

### `.github/workflows/security-scanning.yml` (Scheduled + main branch)
- ✅ CodeQL SAST
- ✅ Semgrep SAST
- ✅ Trivy container image scanning
- ✅ Snyk dependency analysis
- ✅ Bandit security issue detection
- ✅ Safety dependency checker
- ✅ Gitleaks full repository scan
- ✅ TruffleHog secret detection
- ✅ OWASP Dependency Check

**Schedule:**
- Daily at 2 AM UTC (CodeQL, Semgrep, Trivy, Snyk, Safety, Gitleaks full, TruffleHog, OWASP)
- Weekly Mondays (Dependabot pip, GitHub Actions, Docker)

## Results & Reporting

### GitHub Security Tab
All scanning results appear in:
- **Settings → Security → Code scanning alerts**
- **Pull Requests → Checks → Details**

### SARIF Uploads
Multiple tools upload results in SARIF format:
- CodeQL
- Semgrep
- Trivy
- OWASP Dependency Check

View timeline and trends in GitHub Security dashboard.

### Artifacts
Download detailed reports:
- Bandit JSON report
- TruffleHog JSON results
- OWASP Dependency Check HTML report

## Best Practices

### Local Development
1. **Install pre-commit hooks:**
   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. **Run security scans before committing:**
   ```bash
   bandit -r .
   pip-audit -r requirements.txt
   semgrep --config p/security-audit .
   ```

3. **Never commit credentials:**
   - Use `.env` (which is gitignored)
   - Pre-commit hooks will prevent accidental commits
   - Use AWS/Azure/GCP secret managers for production

### Pull Request Workflow
1. All security checks must pass before merge
2. Address alerts in GitHub Security tab
3. Dependency updates are auto-reviewed by Dependabot
4. High-severity vulnerabilities block merge

### Incident Response
If a vulnerability is discovered in production:
1. **Immediate:** Emergency patch release
2. **CI:** Run full security scan suite
3. **Audit:** Review scan history for missed detections
4. **Update:** Add custom rules if gap detected
5. **Alert:** Add secret to gitleaks config if it was leaked

## Configuration Files

### Secret Scanning Patterns
Managed by GitHub (.github/secret_patterns.json if custom):
```json
{
  "patterns": [
    {
      "pattern": "VELAR_API_KEY=[A-Za-z0-9_-]{32,}",
      "message": "Possible Velar API key"
    }
  ]
}
```

### Gitleaks Custom Config (if needed)
Create `.gitleaksignore` to exclude false positives:
```
# Format: <rule_id>:<secret>
generic_api_key:test_key_do_not_scan
```

### Semgrep Custom Rules
Create `.semgrep.yml` in root:
```yaml
rules:
  - id: no-hardcoded-mongo-uri
    pattern: MONGODB_URI = "..."
    message: Do not hardcode MongoDB URI
    severity: ERROR
```

## Monitoring & Alerting

### GitHub Advanced Security (Enterprise feature)
- Automatic alert on new CVE for dependencies
- Dependency and code scanning analytics
- Custom alert webhooks

### Local Monitoring
```bash
# Check for known vulnerabilities weekly
pip-audit -r requirements.txt

# Audit Docker image before release
trivy image velar:latest --severity HIGH,CRITICAL
```

## Troubleshooting

### CodeQL initialization fails
```bash
# Update codeql CLI
gh extension upgrade gh-codeql
codeql version
```

### Trivy scanning timeouts
Increase timeout in workflow:
```yaml
timeout-minutes: 60
```

### Dependabot PR not opening
Check `.github/dependabot.yml` syntax (YAML must be exact)
Verify GitHub.com token has necessary permissions

## References

- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [CodeQL Documentation](https://codeql.github.com/docs/)
- [Semgrep Rules](https://semgrep.dev/r)
- [Trivy Repository](https://github.com/aquasecurity/trivy)
- [OWASP Dependency Check](https://owasp.org/www-project-dependency-check/)
