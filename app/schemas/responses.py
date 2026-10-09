"""Account usage; indicator responses keep dynamic parameter-based column names."""

from pydantic import BaseModel


class StatusResponse(BaseModel):
    username: str
    subscription: str
    requests_today: int
    max_requests_per_day: str
    requests_remaining: str
    last_request_date: str
