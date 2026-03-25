"""
Data classes for Job, Application, and Outreach records.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    id: Optional[int]
    url: str
    url_hash: str
    title: str
    company: str
    location: Optional[str]
    description: Optional[str]
    source: Optional[str]
    date_discovered: Optional[datetime]
    match_score: Optional[int]
    match_rationale: Optional[str]
    status: str = "discovered"
    workday_portal: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "Job":
        return cls(
            id=row["id"],
            url=row["url"],
            url_hash=row["url_hash"],
            title=row["title"],
            company=row["company"],
            location=row.get("location"),
            description=row.get("description"),
            source=row.get("source"),
            date_discovered=row.get("date_discovered"),
            match_score=row.get("match_score"),
            match_rationale=row.get("match_rationale"),
            status=row.get("status", "discovered"),
            workday_portal=row.get("workday_portal"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class Application:
    id: Optional[int]
    job_id: int
    resume_path: Optional[str]
    cover_letter_path: Optional[str]
    applied_at: Optional[datetime]
    method: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "Application":
        return cls(
            id=row["id"],
            job_id=row["job_id"],
            resume_path=row.get("resume_path"),
            cover_letter_path=row.get("cover_letter_path"),
            applied_at=row.get("applied_at"),
            method=row.get("method"),
            notes=row.get("notes"),
            created_at=row.get("created_at"),
        )


@dataclass
class Outreach:
    id: Optional[int]
    job_id: Optional[int]
    company: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    contact_title: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]
    sent_at: Optional[datetime]
    followup_scheduled_at: Optional[datetime]
    followup_sent_at: Optional[datetime]
    response_received: bool = False
    notes: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "Outreach":
        return cls(
            id=row["id"],
            job_id=row.get("job_id"),
            company=row["company"],
            contact_name=row.get("contact_name"),
            contact_email=row.get("contact_email"),
            contact_title=row.get("contact_title"),
            email_subject=row.get("email_subject"),
            email_body=row.get("email_body"),
            sent_at=row.get("sent_at"),
            followup_scheduled_at=row.get("followup_scheduled_at"),
            followup_sent_at=row.get("followup_sent_at"),
            response_received=bool(row.get("response_received", False)),
            notes=row.get("notes"),
            created_at=row.get("created_at"),
        )
