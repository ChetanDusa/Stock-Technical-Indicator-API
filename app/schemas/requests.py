"""Typed query models validated by FastAPI before endpoint execution."""

import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class IndicatorParams(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9&.^_=:-]+$")
    start: datetime.date
    end: datetime.date

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


class SmaParams(IndicatorParams):
    window: int = Field(14, gt=0, le=1095)


class EmaParams(IndicatorParams):
    span: int = Field(14, gt=0, le=1095)


class RsiParams(IndicatorParams):
    period: int = Field(14, gt=1, le=1095)


class MacdParams(IndicatorParams):
    fast: int = Field(12, gt=0, le=1095)
    slow: int = Field(26, gt=0, le=1095)
    signal: int = Field(9, gt=0, le=1095)

    @model_validator(mode="after")
    def validate_windows(self):
        if self.fast >= self.slow:
            raise ValueError("MACD fast must be strictly less than slow")
        return self


class BollingerParams(IndicatorParams):
    period: int = Field(20, gt=1, le=1095)
    std_multiplier: float = Field(2.0, gt=0, le=100)
