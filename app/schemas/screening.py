"""Typed screening conditions, including scalar and indicator-reference operands."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ALIASES = {
    "BOLLINGER_UPPER": ("BOLLINGER", "band", "upper"),
    "BOLLINGER_LOWER": ("BOLLINGER", "band", "lower"),
    "BOLLINGER_MID": ("BOLLINGER", "band", "mid"),
    "MACD_SIGNAL": ("MACD", "component", "signal"),
    "MACD_HIST": ("MACD", "component", "hist"),
}


class IndicatorRef(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    indicator: str
    period: int | None = Field(default=None, gt=0, le=1095)
    fast: int | None = Field(default=None, gt=0, le=1095)
    slow: int | None = Field(default=None, gt=0, le=1095)
    signal_period: int | None = Field(default=None, gt=0, le=1095)
    std_multiplier: float | None = Field(default=None, gt=0, le=100)
    band: Literal["upper", "mid", "lower"] | None = None
    component: Literal["macd", "signal", "hist"] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_indicator(cls, values: Any):
        if not isinstance(values, dict):
            return values
        values = dict(values)
        name = values.get("indicator")
        if isinstance(name, str):
            name = name.upper()
            if name in _ALIASES:
                name, field, alias_value = _ALIASES[name]
                if values.get(field) is not None and values[field] != alias_value:
                    raise ValueError(f"Alias conflicts with {field}")
                values[field] = alias_value
            values["indicator"] = name
        return values

    @field_validator("band", "component", mode="before")
    @classmethod
    def normalize_component(cls, value):
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_parameters(self):
        name = self.indicator
        allowed = {
            "PRICE": set(),
            "SMA": {"period"},
            "EMA": {"period"},
            "RSI": {"period"},
            "MACD": {"fast", "slow", "signal_period", "component"},
            "BOLLINGER": {"period", "std_multiplier", "band"},
        }
        if name not in allowed:
            raise ValueError(f"Unsupported indicator: {name}")
        supplied = {
            field
            for field in (
                "period",
                "fast",
                "slow",
                "signal_period",
                "std_multiplier",
                "band",
                "component",
            )
            if getattr(self, field) is not None
        }
        if supplied - allowed[name]:
            raise ValueError(f"{name} does not accept {sorted(supplied - allowed[name])}")
        if name in {"SMA", "EMA", "RSI", "BOLLINGER"} and self.period is None:
            raise ValueError(f"{name} requires a period")
        if name in {"RSI", "BOLLINGER"} and self.period <= 1:
            raise ValueError(f"{name} requires a period > 1")
        if name == "MACD" and (self.fast or 12) >= (self.slow or 26):
            raise ValueError("MACD fast must be strictly less than slow")
        return self


class ScreeningCondition(IndicatorRef):
    operator: Literal["<", "<=", ">", ">=", "==", "!="]
    value: float | None = None
    reference: IndicatorRef | None = None

    @model_validator(mode="after")
    def validate_operand(self):
        if (self.value is None) == (self.reference is None):
            raise ValueError("Provide exactly one of value or reference")
        return self


class ScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conditions: list[ScreeningCondition] = Field(min_length=1, max_length=10)
    logic: Literal["AND", "OR"] = "AND"

    @field_validator("logic", mode="before")
    @classmethod
    def normalize_logic(cls, value):
        return value.upper() if isinstance(value, str) else value


class ScreeningResponse(BaseModel):
    matched_symbols: list[str]
    count: int
    conditions_evaluated: int
