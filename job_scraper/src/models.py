from dataclasses import dataclass


@dataclass
class JobPosting:
    platform: str  # "CrowdWorks" or "ココナラ"
    title: str
    category: str
    budget_text: str
    deadline_text: str
    url: str
    detected_at: str
