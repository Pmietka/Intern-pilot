# InternPilot

A production-grade Python CLI that automates the finance internship application lifecycle: discovering jobs, scoring them against your profile, generating tailored application materials, submitting Workday applications via AI browser automation, sending recruiter outreach emails, and tracking everything in a local SQLite database.

## What It Does

| Command | What happens |
|---|---|
| `internpilot discover` | Scrapes LinkedIn, Indeed, Glassdoor, ZipRecruiter, Google Jobs for matching internships |
| `internpilot score` | Sends each job to Claude for a 1-10 fit score against your profile |
| `internpilot generate --job-id 42` | Claude rewrites your resume bullets, writes a cover letter, and drafts a recruiter email |
| `internpilot apply --job-id 42 --supervised` | Browser Use AI agent fills out the Workday form while you watch |
| `internpilot outreach --job-id 42` | Sends recruiter cold email via Gmail API |
| `internpilot outreach --followups` | Sends all scheduled follow-up emails that are past due |
| `internpilot status` | Prints a dashboard: total jobs, applied, interviews, offers |
| `internpilot export --csv` | Exports the full tracker to a CSV file |

---

## Requirements

- **Python 3.11+**
- **Windows 11 / macOS / Linux**
- **Google Chrome** (required by Browser Use for Workday automation)
- An **Anthropic API key** (Claude Sonnet)
- A **Google Cloud project** with Gmail API enabled (for email outreach)

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd internpilot
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright browsers (required by Browser Use)

```bash
playwright install chromium
```

### 4. Configure your environment

Copy the example env file and fill in your API keys:

```bash
cp config/.env.example config/.env
```

Edit `config/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_CREDENTIALS_PATH=C:/path/to/google_credentials.json
GOOGLE_TOKEN_PATH=config/token.json
```

### 5. Fill in your profile

Edit `config/profile.yaml` and replace all `[FILL IN]` placeholders with your real information:

```yaml
personal:
  first_name: "Patrick"
  last_name: "YourLastName"
  email: "you@example.com"
  phone: "312-555-0000"
  ...
```

### 6. Configure target employers

Edit `config/employers.yaml` to add Workday portal URLs for your target companies.

### 7. Validate configuration

```bash
python -m src.cli config --validate
```

### 8. Install as CLI tool (optional)

```bash
pip install -e .
```

This makes `internpilot` available system-wide.

---

## Gmail API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use existing)
3. Enable the **Gmail API**
4. Create **OAuth 2.0 credentials** (Desktop app type)
5. Download `credentials.json` and set `GOOGLE_CREDENTIALS_PATH` in your `.env`
6. On first use, a browser window will open for you to authorize the app
7. The token is saved to `config/token.json` automatically

---

## Usage

### Discover jobs

```bash
# Scrape all configured job boards
internpilot discover

# LinkedIn only
internpilot discover --source linkedin

# Workday portals only (requires Browser Use)
internpilot discover --workday

# Preview without saving
internpilot discover --dry-run
```

### Score jobs

```bash
# Score all unscored jobs
internpilot score

# Score one specific job
internpilot score --job-id 42
```

### Generate application materials

```bash
# Full generation: resume + cover letter + email draft
internpilot generate --job-id 42

# All jobs scoring 7 or higher
internpilot generate --all

# Resume only
internpilot generate --resume-only 42

# Email draft only
internpilot generate --email-only 42
```

Generated files are saved to:
- `outputs/resumes/resume_CompanyName_JobTitle_42.docx`
- `outputs/cover_letters/cover_letter_CompanyName_42.txt`
- `outputs/emails/outreach_CompanyName_42.txt`

### Apply to jobs

```bash
# Apply to one job (supervised: pauses for your confirmation at uncertain fields)
internpilot apply --job-id 42 --supervised

# Apply to all jobs with generated content (supervised by default)
internpilot apply --batch

# Dry run: show what would happen
internpilot apply --job-id 42 --dry-run
```

The Workday agent will:
1. Open a visible Chrome window so you can watch
2. Navigate to the application portal and click Apply
3. Fill every form field using your profile data
4. Pause and prompt you in the terminal for any field it cannot confidently fill
5. Ask for your confirmation before clicking Submit

### Send outreach emails

```bash
# Generate and send a recruiter email
internpilot outreach --job-id 42 \
  --contact-name "Jane Smith" \
  --contact-email "jane.smith@firm.com" \
  --contact-title "Campus Recruiter"

# Send all follow-ups that are due
internpilot outreach --followups

# Preview without sending
internpilot outreach --job-id 42 --dry-run
```

### Track status

```bash
# Full dashboard
internpilot status

# Details for one job
internpilot status --job-id 42

# All applied jobs
internpilot status --applied

# Jobs with content ready but not applied
internpilot status --pending

# Export to CSV
internpilot export --csv
internpilot export --csv --output tracker_march.csv
```

---

## Project Structure

```
internpilot/
├── config/
│   ├── profile.yaml              # Your profile: personal info, education, experience
│   ├── employers.yaml            # Target companies and Workday portal URLs
│   ├── searches.yaml             # Job search queries and filters
│   ├── templates/                # Jinja2 email and cover letter templates
│   └── .env                      # API keys (gitignored)
├── src/
│   ├── cli.py                    # Click CLI commands
│   ├── discovery/
│   │   ├── scraper.py            # python-jobspy multi-board scraping
│   │   ├── workday_scraper.py    # Browser Use Workday portal scraping
│   │   └── dedup.py              # URL hash deduplication
│   ├── scoring/
│   │   └── matcher.py            # Claude API job scoring (1-10)
│   ├── content/
│   │   ├── resume_tailor.py      # AI resume rewriting + .docx generation
│   │   ├── cover_letter.py       # AI cover letter generation
│   │   └── email_drafter.py      # Recruiter outreach + follow-up email drafting
│   ├── applicant/
│   │   ├── workday_agent.py      # Browser Use agent for Workday applications
│   │   └── form_filler.py        # Profile-to-form-field mapping
│   ├── outreach/
│   │   ├── email_sender.py       # Gmail API sending
│   │   └── scheduler.py          # Follow-up scheduling
│   ├── tracker/
│   │   ├── database.py           # SQLite CRUD operations
│   │   └── models.py             # Job, Application, Outreach data classes
│   └── utils/
│       ├── llm.py                # Anthropic API wrapper
│       └── config_loader.py      # YAML and .env loading
├── outputs/
│   ├── resumes/                  # Generated resume .docx files
│   ├── cover_letters/            # Generated cover letter .txt files
│   ├── emails/                   # Drafted email .txt files
│   └── screenshots/              # Browser automation screenshots
├── logs/
│   └── internpilot.log           # Application log file
├── main.py                       # Alternative entry: python main.py <command>
├── requirements.txt
└── .gitignore
```

---

## Database Schema

SQLite database at `internpilot/internpilot.db`:

- **jobs**: URL-deduplicated job listings with match scores and status tracking
- **applications**: Application records linking to jobs, resume/cover letter paths, submission timestamps
- **outreach**: Recruiter email records with follow-up scheduling and response tracking

Status progression: `discovered` → `scored` → `content_generated` → `applied` → `interview` / `offer` / `rejected`

---

## Configuration Details

### searches.yaml filters

```yaml
filters:
  min_match_score: 7        # Only process jobs scoring 7+ out of 10
  max_applications_per_day: 10
  cooldown_days_per_company: 90
```

### Rate limiting

The tool respects API rate limits automatically:
- 2 second delay between Claude API calls
- 3 second delay between browser page actions

Override via environment variables:
```
CLAUDE_API_DELAY_SECONDS=2
BROWSER_ACTION_DELAY_SECONDS=3
```

---

## Tips for Daily Use

1. **Morning routine**: Run `discover`, then `score`, then `generate --all` for any 7+ jobs
2. **Apply session**: Run `apply --batch --supervised` to review each application before submission
3. **Outreach**: After applying, run `outreach --job-id X --contact-email ...` to reach out to recruiters
4. **End of week**: Run `outreach --followups` to send any due follow-ups
5. **Track progress**: `status` for the dashboard, `export --csv` for spreadsheet analysis

---

## Troubleshooting

**`ANTHROPIC_API_KEY is not set`**: Copy `config/.env.example` to `config/.env` and add your key.

**`python-jobspy is not installed`**: Run `pip install python-jobspy`

**Browser does not open**: Ensure `playwright install chromium` was run after installing requirements.

**Gmail auth fails**: Delete `config/token.json` and re-run to trigger fresh OAuth flow.

**Job descriptions not loading**: Some boards (LinkedIn) require login. python-jobspy handles this automatically but descriptions may be incomplete without an account.

---

## Architecture Notes

- **Idempotent by design**: Running `discover` twice will not create duplicate jobs (URL hash deduplication). Running `generate` twice for the same job overwrites output files.
- **Graceful degradation**: If the Claude API is unavailable, you can still view discovered jobs and update statuses manually. If Browser Use fails mid-application, the partial state is logged.
- **No secrets in code**: All API keys loaded from `config/.env` via python-dotenv. The `.env` file is gitignored.
- **Dry run support**: Every write action (`discover`, `apply`, `outreach`) supports `--dry-run` for safe previewing.
