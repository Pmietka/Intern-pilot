"""
InternPilot GUI — NiceGUI web application.
Run with: python gui.py
Opens at http://localhost:8080
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Fix Windows asyncio before anything else
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, run, app

from src.utils.config_loader import (
    load_env,
    load_profile,
    validate_configs,
    scan_for_placeholders,
)
from src.tracker.database import Database

load_env()

DB_PATH = Path(__file__).parent / "internpilot.db"


def get_db() -> Database:
    return Database(DB_PATH)


# ─────────────────────────────────────────────────────────────
# Log handler that streams to a NiceGUI ui.log widget
# ─────────────────────────────────────────────────────────────

class _UILogHandler(logging.Handler):
    def __init__(self, log_widget):
        super().__init__()
        self._widget = log_widget
        self.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))

    def emit(self, record):
        try:
            msg = self.format(record)
            self._widget.push(msg)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────
# Shared nav sidebar
# ─────────────────────────────────────────────────────────────

def _sidebar():
    with ui.left_drawer(fixed=True).style(
        "background: #0f172a; padding: 1.5rem 1rem; min-width: 200px;"
    ):
        ui.label("InternPilot").style(
            "color: white; font-size: 1.3rem; font-weight: 700; margin-bottom: 2rem; display: block;"
        )
        pages = [
            ("📊", "Dashboard", "/"),
            ("🔍", "Jobs", "/jobs"),
            ("✅", "Review Queue", "/review"),
            ("📧", "Outreach", "/outreach"),
            ("🏆", "Outcomes", "/outcomes"),
            ("⚙️", "Settings", "/settings"),
        ]
        for icon, label, path in pages:
            ui.link(f"{icon}  {label}", path).style(
                "color: #94a3b8; display: block; padding: 0.5rem 0.75rem; "
                "border-radius: 6px; text-decoration: none; margin-bottom: 4px; "
                "font-size: 0.95rem;"
            )


def _header(title: str):
    ui.label(title).style(
        "font-size: 1.6rem; font-weight: 700; color: #1e293b; margin-bottom: 1.5rem;"
    )


def _card(content_fn, **kwargs):
    with ui.card().style(
        "border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.08); "
        "padding: 1.25rem; border: 1px solid #e2e8f0;" + kwargs.get("style", "")
    ):
        content_fn()


# ─────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────

@ui.page("/")
def page_dashboard():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Dashboard")

        db = get_db()
        stats = db.get_summary_stats()

        # KPI row
        kpis = [
            ("Discovered", stats.get("discovered", 0), "#3b82f6"),
            ("Scored", stats.get("scored", 0), "#8b5cf6"),
            ("Applied", stats.get("applied", 0), "#10b981"),
            ("Interviews", stats.get("interview", 0), "#f59e0b"),
            ("Offers", stats.get("offer", 0), "#22c55e"),
            ("Rejected", stats.get("rejected", 0), "#ef4444"),
        ]

        with ui.row().style("gap: 1rem; flex-wrap: wrap; margin-bottom: 2rem;"):
            for label, value, color in kpis:
                with ui.card().style(
                    f"border-radius: 10px; padding: 1rem 1.5rem; min-width: 130px; "
                    f"border-left: 4px solid {color}; border: 1px solid #e2e8f0;"
                ):
                    ui.label(str(value)).style(
                        f"font-size: 2rem; font-weight: 700; color: {color}; line-height: 1;"
                    )
                    ui.label(label).style("color: #64748b; font-size: 0.85rem; margin-top: 4px;")

        # Pipeline controls + log
        with ui.row().style("gap: 1.5rem; width: 100%; align-items: flex-start;"):

            # Pipeline run panel
            with ui.card().style(
                "border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0; flex: 0 0 320px;"
            ):
                ui.label("Run Pipeline").style(
                    "font-size: 1.1rem; font-weight: 600; margin-bottom: 1rem;"
                )

                source_select = ui.select(
                    options=["all", "linkedin", "indeed", "glassdoor", "ziprecruiter", "google"],
                    value="all",
                    label="Job Board",
                ).style("margin-bottom: 0.75rem;")

                skip_apply_toggle = ui.switch("Skip apply step", value=True).style(
                    "margin-bottom: 0.5rem;"
                )
                dry_run_toggle = ui.switch("Dry run (no saves)", value=False).style(
                    "margin-bottom: 1rem;"
                )

                run_btn = ui.button("▶  Run Now", color="primary").style(
                    "width: 100%; font-weight: 600;"
                )

                ui.separator().style("margin: 1rem 0;")
                ui.label("Schedule").style("font-weight: 600; margin-bottom: 0.5rem;")
                schedule_time = ui.input("Daily time (HH:MM)", value="08:00").style(
                    "margin-bottom: 0.75rem;"
                )
                schedule_btn = ui.button("🕐  Enable Daily Schedule", color="secondary").style(
                    "width: 100%;"
                )

            # Log output
            with ui.card().style(
                "border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0; flex: 1;"
            ):
                ui.label("Pipeline Log").style(
                    "font-size: 1.1rem; font-weight: 600; margin-bottom: 0.75rem;"
                )
                log = ui.log(max_lines=200).style(
                    "height: 340px; font-size: 0.8rem; font-family: monospace; "
                    "background: #0f172a; color: #e2e8f0; border-radius: 8px; padding: 0.75rem;"
                )

        # Recent top jobs
        ui.label("Top Scored Jobs").style(
            "font-size: 1.1rem; font-weight: 600; margin-top: 2rem; margin-bottom: 0.75rem;"
        )
        top_jobs = db.get_jobs_by_min_score(7)[:10]
        if top_jobs:
            rows = [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "score": j.match_score,
                    "status": j.status,
                    "source": j.source or "",
                }
                for j in top_jobs
            ]
            ui.aggrid({
                "columnDefs": [
                    {"field": "id", "width": 70},
                    {"field": "title", "flex": 2},
                    {"field": "company", "flex": 1},
                    {"field": "score", "width": 90},
                    {"field": "status", "width": 150},
                    {"field": "source", "width": 120},
                ],
                "rowData": rows,
                "defaultColDef": {"sortable": True},
            }).style("height: 280px;")
        else:
            ui.label("No scored jobs yet. Run the pipeline to get started.").style("color: #64748b;")

        # Wire up run button
        async def _run_pipeline():
            from src.cli import _run_pipeline_once
            run_btn.disable()
            log.clear()
            handler = _UILogHandler(log)
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            try:
                log.push(f"[{datetime.now():%H:%M:%S}] Pipeline started...")
                await run.io_bound(
                    _run_pipeline_once,
                    source=source_select.value,
                    skip_apply=skip_apply_toggle.value,
                    dry_run=dry_run_toggle.value,
                )
                log.push(f"[{datetime.now():%H:%M:%S}] Pipeline complete.")
                ui.notify("Pipeline finished!", type="positive")
            except Exception as exc:
                log.push(f"[ERROR] {exc}")
                ui.notify(f"Pipeline error: {exc}", type="negative")
            finally:
                root_logger.removeHandler(handler)
                run_btn.enable()

        run_btn.on_click(_run_pipeline)

        async def _enable_schedule():
            ui.notify(
                f"To run on a schedule, use the CLI: internpilot schedule --time {schedule_time.value}",
                type="info",
                timeout=6000,
            )

        schedule_btn.on_click(_enable_schedule)


# ─────────────────────────────────────────────────────────────
# Jobs
# ─────────────────────────────────────────────────────────────

@ui.page("/jobs")
def page_jobs():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Jobs")

        db = get_db()

        # Filter bar
        with ui.row().style("gap: 1rem; margin-bottom: 1rem; align-items: center;"):
            status_filter = ui.select(
                options=["all", "discovered", "scored", "content_generated", "applied",
                         "interview", "offer", "rejected"],
                value="all",
                label="Filter by Status",
            ).style("min-width: 180px;")
            min_score_input = ui.number("Min Score", value=0, min=0, max=10).style("width: 120px;")
            refresh_btn = ui.button("Refresh", icon="refresh", color="grey")

        jobs_grid = ui.aggrid({
            "columnDefs": [
                {"field": "id", "width": 70, "pinned": "left"},
                {"field": "title", "flex": 2, "filter": True},
                {"field": "company", "flex": 1, "filter": True},
                {"field": "location", "flex": 1, "filter": True},
                {"field": "score", "width": 90, "sortable": True},
                {"field": "status", "width": 150, "filter": True},
                {"field": "source", "width": 110},
                {"field": "discovered", "width": 140},
            ],
            "rowData": [],
            "defaultColDef": {"sortable": True, "resizable": True},
            "pagination": True,
            "paginationPageSize": 25,
        }).style("height: 480px;")

        # Detail panel
        detail_panel = ui.card().style(
            "border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0; "
            "margin-top: 1.5rem; display: none;"
        )
        detail_content = ui.column()

        def _load_jobs():
            jobs = db.get_all_jobs(
                status=None if status_filter.value == "all" else status_filter.value
            )
            min_s = int(min_score_input.value or 0)
            rows = [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location or "",
                    "score": j.match_score or 0,
                    "status": j.status,
                    "source": j.source or "",
                    "discovered": str(j.date_discovered or "")[:10],
                }
                for j in jobs
                if (j.match_score or 0) >= min_s
            ]
            jobs_grid.options["rowData"] = rows
            jobs_grid.update()

        _load_jobs()

        async def _on_row_click(e):
            job_id = e.args["data"]["id"]
            job = db.get_job(job_id)
            app_rec = db.get_application(job_id)
            outreaches = db.get_outreach_for_job(job_id)

            detail_panel.style("display: block;")
            detail_content.clear()
            with detail_content:
                with ui.row().style("justify-content: space-between; align-items: flex-start;"):
                    with ui.column():
                        ui.label(f"{job.title}").style("font-size: 1.2rem; font-weight: 700;")
                        ui.label(f"{job.company}  ·  {job.location or 'N/A'}").style("color: #64748b;")
                    with ui.column().style("align-items: flex-end;"):
                        score_color = "#22c55e" if (job.match_score or 0) >= 8 else (
                            "#f59e0b" if (job.match_score or 0) >= 6 else "#ef4444"
                        )
                        ui.label(f"{job.match_score or '—'}/10").style(
                            f"font-size: 1.5rem; font-weight: 700; color: {score_color};"
                        )
                        # Status updater
                        new_status = ui.select(
                            options=["discovered", "scored", "content_generated", "applied",
                                     "interview", "offer", "rejected"],
                            value=job.status,
                            label="Status",
                        ).style("min-width: 160px;")

                        def _update_status(job_id=job_id):
                            db.update_job_status(job_id, new_status.value)
                            ui.notify(f"Status updated to {new_status.value}", type="positive")
                            _load_jobs()

                        ui.button("Update", on_click=_update_status, color="primary").style(
                            "margin-top: 4px;"
                        )

                ui.separator()

                if job.match_rationale:
                    ui.label("AI Rationale").style("font-weight: 600; margin-top: 0.5rem;")
                    ui.label(job.match_rationale).style("color: #475569; font-size: 0.9rem;")

                with ui.row().style("gap: 1rem; margin-top: 0.75rem;"):
                    ui.link("Open Job Listing ↗", job.url, new_tab=True)
                    if app_rec and app_rec.resume_path:
                        ui.label(f"Resume: {Path(app_rec.resume_path).name}").style(
                            "color: #64748b; font-size: 0.85rem;"
                        )

                if job.description:
                    with ui.expansion("Job Description").style("margin-top: 0.5rem;"):
                        ui.label(job.description[:3000]).style(
                            "font-size: 0.85rem; color: #475569; white-space: pre-wrap;"
                        )

        jobs_grid.on("cellClicked", _on_row_click)
        status_filter.on_value_change(lambda _: _load_jobs())
        min_score_input.on_value_change(lambda _: _load_jobs())
        refresh_btn.on_click(lambda: _load_jobs())


# ─────────────────────────────────────────────────────────────
# Review Queue
# ─────────────────────────────────────────────────────────────

@ui.page("/review")
def page_review():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Review Queue")

        db = get_db()
        pending = db.get_jobs_pending_review()

        if not pending:
            with ui.card().style("padding: 2rem; text-align: center; border: 1px solid #e2e8f0; border-radius: 12px;"):
                ui.label("✅ Nothing to review.").style("font-size: 1.1rem; color: #64748b;")
                ui.label("Run the pipeline to generate content, then come back here.").style(
                    "color: #94a3b8; margin-top: 0.5rem;"
                )
            return

        ui.label(f"{len(pending)} job(s) awaiting review.").style(
            "color: #64748b; margin-bottom: 1.5rem;"
        )

        job_container = ui.column().style("width: 100%; gap: 1.5rem;")

        def _render_review_cards():
            job_container.clear()
            pending_now = db.get_jobs_pending_review()
            if not pending_now:
                with job_container:
                    ui.label("✅ All jobs reviewed!").style("color: #22c55e; font-size: 1.1rem;")
                return

            with job_container:
                for job in pending_now:
                    app_rec = db.get_application(job.id)
                    outreaches = db.get_outreach_for_job(job.id)

                    with ui.card().style(
                        "border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0; width: 100%;"
                    ):
                        with ui.row().style("justify-content: space-between; align-items: center; margin-bottom: 1rem;"):
                            with ui.column():
                                ui.label(job.title).style("font-size: 1.1rem; font-weight: 700;")
                                ui.label(f"{job.company}  ·  Score: {job.match_score}/10").style(
                                    "color: #64748b;"
                                )
                            with ui.row().style("gap: 0.75rem;"):
                                def _approve(jid=job.id):
                                    db.approve_content(jid)
                                    ui.notify(f"Job {jid} approved!", type="positive")
                                    _render_review_cards()

                                def _skip(jid=job.id):
                                    db.update_job_status(jid, "rejected")
                                    ui.notify(f"Job {jid} skipped.", type="warning")
                                    _render_review_cards()

                                ui.button("✓ Approve", on_click=_approve, color="positive").style(
                                    "font-weight: 600;"
                                )
                                ui.button("✗ Skip", on_click=_skip, color="negative")

                        with ui.tabs().style("margin-bottom: 0.5rem;") as tabs:
                            cover_tab = ui.tab("Cover Letter")
                            email_tab = ui.tab("Recruiter Email")
                            if app_rec and app_rec.resume_path:
                                ui.tab("Resume Path")

                        with ui.tab_panels(tabs, value=cover_tab):
                            with ui.tab_panel(cover_tab):
                                if app_rec and app_rec.cover_letter_path:
                                    cl_path = Path(app_rec.cover_letter_path)
                                    if cl_path.exists():
                                        text = cl_path.read_text(encoding="utf-8")
                                        ui.textarea(value=text).style(
                                            "width: 100%; height: 220px; font-size: 0.85rem;"
                                        )
                                    else:
                                        ui.label(f"File not found: {cl_path}").style("color: #ef4444;")
                                else:
                                    ui.label("No cover letter generated yet.").style("color: #94a3b8;")

                            with ui.tab_panel(email_tab):
                                if outreaches:
                                    o = outreaches[0]
                                    ui.label(f"Subject: {o.email_subject or '—'}").style(
                                        "font-weight: 600; margin-bottom: 0.5rem;"
                                    )
                                    ui.textarea(value=o.email_body or "").style(
                                        "width: 100%; height: 160px; font-size: 0.85rem;"
                                    )
                                else:
                                    ui.label("No email draft generated yet.").style("color: #94a3b8;")

                            if app_rec and app_rec.resume_path:
                                with ui.tab_panel(ui.tab("Resume Path")):
                                    ui.label(app_rec.resume_path).style(
                                        "font-family: monospace; font-size: 0.85rem; "
                                        "background: #f1f5f9; padding: 0.5rem; border-radius: 6px;"
                                    )

        _render_review_cards()


# ─────────────────────────────────────────────────────────────
# Outreach
# ─────────────────────────────────────────────────────────────

@ui.page("/outreach")
def page_outreach():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Outreach")

        db = get_db()

        with ui.row().style("gap: 1.5rem; width: 100%; align-items: flex-start;"):

            # Outreach table
            with ui.column().style("flex: 2;"):
                ui.label("Sent Outreach").style("font-weight: 600; margin-bottom: 0.75rem;")

                with db._conn() as conn:
                    rows_raw = conn.execute("""
                        SELECT o.id, j.title, o.company, o.contact_name,
                               o.contact_email, o.sent_at, o.followup_scheduled_at,
                               o.followup_sent_at, o.response_received
                        FROM outreach o
                        LEFT JOIN jobs j ON o.job_id = j.id
                        ORDER BY o.created_at DESC
                    """).fetchall()

                outreach_rows = [
                    {
                        "id": r["id"],
                        "job": r["title"] or "—",
                        "company": r["company"],
                        "contact": r["contact_name"] or "—",
                        "email": r["contact_email"] or "—",
                        "sent": str(r["sent_at"] or "pending")[:16],
                        "followup": str(r["followup_scheduled_at"] or "—")[:10],
                        "response": "✓" if r["response_received"] else "—",
                    }
                    for r in rows_raw
                ]

                ui.aggrid({
                    "columnDefs": [
                        {"field": "job", "flex": 2, "filter": True},
                        {"field": "company", "flex": 1, "filter": True},
                        {"field": "contact", "flex": 1},
                        {"field": "sent", "width": 140},
                        {"field": "followup", "width": 120},
                        {"field": "response", "width": 100},
                    ],
                    "rowData": outreach_rows,
                    "defaultColDef": {"sortable": True, "resizable": True},
                }).style("height: 320px;")

            # Contact finder
            with ui.card().style(
                "flex: 1; border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0;"
            ):
                ui.label("Find Recruiter Contacts").style(
                    "font-weight: 600; font-size: 1rem; margin-bottom: 1rem;"
                )
                company_input = ui.input("Company name", placeholder="JPMorgan Chase").style(
                    "width: 100%; margin-bottom: 0.75rem;"
                )
                domain_input = ui.input("Domain (optional)", placeholder="jpmorgan.com").style(
                    "width: 100%; margin-bottom: 1rem;"
                )
                find_btn = ui.button("Find Contacts", color="primary").style("width: 100%;")

                results_col = ui.column().style("margin-top: 1rem;")

                async def _find_contacts():
                    from src.outreach.contact_finder import find_recruiter_contacts
                    results_col.clear()
                    if not company_input.value:
                        ui.notify("Enter a company name.", type="warning")
                        return
                    find_btn.disable()
                    with results_col:
                        ui.spinner()
                    contacts = await run.io_bound(
                        find_recruiter_contacts,
                        company=company_input.value,
                        domain=domain_input.value or None,
                    )
                    results_col.clear()
                    with results_col:
                        if not contacts:
                            ui.label("No contacts found. Check HUNTER_API_KEY in .env.").style(
                                "color: #94a3b8; font-size: 0.85rem;"
                            )
                        else:
                            for c in contacts:
                                with ui.card().style(
                                    "padding: 0.75rem; border: 1px solid #e2e8f0; "
                                    "border-radius: 8px; margin-bottom: 0.5rem;"
                                ):
                                    ui.label(c["name"]).style("font-weight: 600; font-size: 0.9rem;")
                                    ui.label(c.get("title", "")).style(
                                        "color: #64748b; font-size: 0.82rem;"
                                    )
                                    ui.label(c["email"]).style(
                                        "font-family: monospace; font-size: 0.82rem; color: #3b82f6;"
                                    )
                    find_btn.enable()

                find_btn.on_click(_find_contacts)


# ─────────────────────────────────────────────────────────────
# Outcomes
# ─────────────────────────────────────────────────────────────

@ui.page("/outcomes")
def page_outcomes():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Outcomes")

        db = get_db()

        with ui.row().style("gap: 1.5rem; width: 100%; align-items: flex-start;"):

            # Update outcome panel
            with ui.card().style(
                "flex: 0 0 300px; border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0;"
            ):
                ui.label("Record Outcome").style("font-weight: 600; margin-bottom: 1rem;")

                applied_jobs = db.get_all_jobs(status="applied")
                interview_jobs = db.get_all_jobs(status="interview")
                eligible = applied_jobs + interview_jobs

                if not eligible:
                    ui.label("No applied jobs to update.").style("color: #94a3b8;")
                else:
                    job_options = {f"{j.id}: {j.title[:35]} @ {j.company[:20]}": j.id for j in eligible}
                    job_select = ui.select(options=list(job_options.keys()), label="Job").style(
                        "width: 100%; margin-bottom: 0.75rem;"
                    )
                    status_select = ui.select(
                        options=["interview", "offer", "rejected"],
                        value="interview",
                        label="Outcome",
                    ).style("width: 100%; margin-bottom: 0.75rem;")
                    stage_input = ui.input(
                        "Stage (optional)", placeholder="phone_screen / superday / final"
                    ).style("width: 100%; margin-bottom: 0.75rem;")
                    date_input = ui.input("Date (YYYY-MM-DD)", placeholder=datetime.now().strftime("%Y-%m-%d")).style(
                        "width: 100%; margin-bottom: 1rem;"
                    )

                    def _record_outcome():
                        if not job_select.value:
                            ui.notify("Select a job.", type="warning")
                            return
                        jid = job_options[job_select.value]
                        db.update_job_status(jid, status_select.value)
                        if stage_input.value or date_input.value:
                            db.update_interview_stage(
                                jid,
                                stage=stage_input.value or status_select.value,
                                interview_date=date_input.value or None,
                            )
                        ui.notify(f"Updated to {status_select.value}!", type="positive")
                        if status_select.value == "interview":
                            ui.notify(
                                "Tip: Go to the Jobs page to draft a thank-you email.",
                                type="info",
                                timeout=5000,
                            )

                    ui.button("Record", on_click=_record_outcome, color="primary").style("width: 100%;")

            # Outcomes summary
            with ui.column().style("flex: 1;"):
                statuses = ["interview", "offer", "rejected"]
                for status in statuses:
                    jobs = db.get_all_jobs(status=status)
                    if not jobs:
                        continue
                    color = {"interview": "#f59e0b", "offer": "#22c55e", "rejected": "#ef4444"}[status]
                    ui.label(f"{status.title()} ({len(jobs)})").style(
                        f"font-weight: 700; color: {color}; margin-top: 1rem; margin-bottom: 0.5rem;"
                    )
                    rows = [
                        {"title": j.title, "company": j.company, "score": j.match_score or "—"}
                        for j in jobs
                    ]
                    ui.aggrid({
                        "columnDefs": [
                            {"field": "title", "flex": 2},
                            {"field": "company", "flex": 1},
                            {"field": "score", "width": 90},
                        ],
                        "rowData": rows,
                        "domLayout": "autoHeight",
                    })


# ─────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────

@ui.page("/settings")
def page_settings():
    _sidebar()

    with ui.column().style("padding: 2rem; width: 100%;"):
        _header("Settings")

        with ui.row().style("gap: 1.5rem; width: 100%; align-items: flex-start;"):

            # Config validation
            with ui.card().style(
                "flex: 1; border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0;"
            ):
                with ui.row().style("justify-content: space-between; align-items: center; margin-bottom: 1rem;"):
                    ui.label("Configuration Status").style("font-weight: 600; font-size: 1rem;")
                    validate_btn = ui.button("Re-check", icon="refresh", color="grey")

                issues_col = ui.column()

                def _run_validation():
                    issues_col.clear()
                    issues = validate_configs()
                    with issues_col:
                        if not issues:
                            with ui.row().style("align-items: center; gap: 0.5rem;"):
                                ui.icon("check_circle", color="green", size="1.5rem")
                                ui.label("All configuration is valid.").style("color: #22c55e; font-weight: 600;")
                        else:
                            for issue in issues:
                                with ui.row().style("align-items: flex-start; gap: 0.5rem; margin-bottom: 0.4rem;"):
                                    ui.icon("warning", color="orange", size="1.2rem")
                                    ui.label(issue).style("color: #b45309; font-size: 0.875rem;")

                _run_validation()
                validate_btn.on_click(_run_validation)

            # Profile summary
            with ui.card().style(
                "flex: 1; border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0;"
            ):
                ui.label("Profile Summary").style("font-weight: 600; font-size: 1rem; margin-bottom: 1rem;")
                try:
                    profile = load_profile()
                    personal = profile.get("personal", {})
                    edu = profile.get("education", [{}])[0]
                    exp = profile.get("experience", [])

                    info = [
                        ("Name", f"{personal.get('first_name', '—')} {personal.get('last_name', '')}"),
                        ("Email", personal.get("email", "—")),
                        ("School", edu.get("institution", "—")),
                        ("Major", edu.get("major", "—")),
                        ("GPA", str(edu.get("gpa", "—"))),
                        ("Grad", edu.get("expected_graduation", "—")),
                        ("Experience entries", str(len(exp))),
                    ]
                    for label, value in info:
                        with ui.row().style("margin-bottom: 0.4rem;"):
                            ui.label(f"{label}:").style(
                                "color: #64748b; font-size: 0.875rem; min-width: 130px;"
                            )
                            ui.label(value).style("font-size: 0.875rem; font-weight: 500;")

                    placeholders = scan_for_placeholders(profile)
                    if placeholders:
                        ui.separator()
                        ui.label(f"⚠ {len(placeholders)} unfilled placeholder(s):").style(
                            "color: #b45309; font-weight: 600; margin-top: 0.5rem;"
                        )
                        for p in placeholders:
                            ui.label(f"  • {p}").style("color: #b45309; font-size: 0.82rem;")

                except Exception as exc:
                    ui.label(f"Could not load profile: {exc}").style("color: #ef4444;")

        # API keys status
        with ui.card().style(
            "border-radius: 12px; padding: 1.5rem; border: 1px solid #e2e8f0; margin-top: 1.5rem;"
        ):
            ui.label("Environment Variables").style("font-weight: 600; font-size: 1rem; margin-bottom: 1rem;")
            import os
            keys = [
                ("ANTHROPIC_API_KEY", "Required for scoring + content generation"),
                ("GOOGLE_CREDENTIALS_PATH", "Required for Gmail outreach"),
                ("HUNTER_API_KEY", "Optional — enables recruiter contact lookup"),
            ]
            for key, desc in keys:
                val = os.getenv(key, "")
                is_set = bool(val)
                with ui.row().style("align-items: center; gap: 0.75rem; margin-bottom: 0.5rem;"):
                    ui.icon(
                        "check_circle" if is_set else "cancel",
                        color="green" if is_set else "red",
                        size="1.2rem",
                    )
                    with ui.column():
                        ui.label(key).style("font-family: monospace; font-size: 0.875rem; font-weight: 600;")
                        ui.label(desc).style("color: #94a3b8; font-size: 0.78rem;")
                    if is_set:
                        ui.label("●●●●●●●●").style("color: #94a3b8; font-size: 0.8rem; margin-left: auto;")
                    else:
                        ui.label("Not set — add to config/.env").style(
                            "color: #ef4444; font-size: 0.8rem; margin-left: auto;"
                        )


# ─────────────────────────────────────────────────────────────
# Launch
# ─────────────────────────────────────────────────────────────

ui.run(
    title="InternPilot",
    port=8080,
    reload=False,
    favicon="🚀",
    dark=False,
)
