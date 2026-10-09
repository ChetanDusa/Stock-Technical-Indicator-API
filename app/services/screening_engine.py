"""Screening Engine — vectorized evaluation of technical screening conditions across symbols.

Evaluates conditions across all symbols in the dataset using native Polars expressions
grouped by symbol (`over("symbol")`).
The signal is evaluated on the latest available trading row per symbol independently.
"""

from __future__ import annotations

from typing import List, Tuple, Union

import polars as pl

from app.schemas.screening import IndicatorRef, ScreeningCondition
from indicators import rsi


class ScreeningEngine:
    """Evaluates screening conditions across multi-symbol Polars DataFrames."""

    @staticmethod
    def get_column_identifier(item: Union[ScreeningCondition, IndicatorRef]) -> Tuple[str, str]:
        """Generate a canonical column name and indicator key for a condition or reference.

        Returns:
            (col_name, indicator_key)
        """
        ind = item.indicator.upper()

        if ind == "PRICE":
            return "close", "PRICE"

        elif ind == "SMA":
            period = item.period
            return f"SMA_{period}", f"SMA:{period}"

        elif ind == "EMA":
            period = item.period
            return f"EMA_{period}", f"EMA:{period}"

        elif ind == "RSI":
            period = item.period
            return f"RSI_{period}", f"RSI:{period}"

        elif ind == "MACD":
            fast = item.fast if item.fast is not None else 12
            slow = item.slow if item.slow is not None else 26
            sig = item.signal_period if item.signal_period is not None else 9
            comp = (item.component or "macd").lower()

            if comp == "signal":
                return f"MACD_Signal_{fast}_{slow}_{sig}", f"MACD_Signal:{fast}:{slow}:{sig}"
            elif comp == "hist":
                return f"MACD_Hist_{fast}_{slow}_{sig}", f"MACD_Hist:{fast}:{slow}:{sig}"
            else:
                return f"MACD_{fast}_{slow}_{sig}", f"MACD:{fast}:{slow}:{sig}"

        elif ind == "BOLLINGER":
            period = item.period
            std = item.std_multiplier if item.std_multiplier is not None else 2.0
            band = (item.band or "mid").lower()

            if band == "upper":
                return f"BB_Upper_{period}_{std}", f"BB_Upper:{period}:{std}"
            elif band == "lower":
                return f"BB_Lower_{period}_{std}", f"BB_Lower:{period}:{std}"
            else:
                return f"BB_Mid_{period}_{std}", f"BB_Mid:{period}:{std}"

        else:
            raise ValueError(f"Unknown indicator: {ind}")

    def compute_indicator_column(
        self,
        df: pl.DataFrame,
        item: Union[ScreeningCondition, IndicatorRef],
    ) -> Tuple[pl.DataFrame, str]:
        """Compute the required indicator column if not already present in df."""
        col_name, _ = self.get_column_identifier(item)
        if col_name in df.columns:
            return df, col_name

        ind = item.indicator.upper()

        if ind == "PRICE":
            # "close" is already in df
            return df, "close"

        elif ind == "SMA":
            period = item.period
            expr = pl.col("close").rolling_mean(window_size=period).over("symbol").alias(col_name)
            df = df.with_columns(expr)
            return df, col_name

        elif ind == "EMA":
            period = item.period
            expr = pl.col("close").ewm_mean(span=period).over("symbol").alias(col_name)
            df = df.with_columns(expr)
            return df, col_name

        elif ind == "RSI":
            period = item.period
            df = rsi(df, period=period, group_by_symbol=True)
            return df, col_name

        elif ind == "MACD":
            fast = item.fast if item.fast is not None else 12
            slow = item.slow if item.slow is not None else 26
            sig = item.signal_period if item.signal_period is not None else 9

            macd_col = f"MACD_{fast}_{slow}_{sig}"
            sig_col = f"MACD_Signal_{fast}_{slow}_{sig}"
            hist_col = f"MACD_Hist_{fast}_{slow}_{sig}"

            # Compute MACD line, Signal line, and Hist line
            if macd_col not in df.columns:
                ema_fast = pl.col("close").ewm_mean(span=fast).over("symbol")
                ema_slow = pl.col("close").ewm_mean(span=slow).over("symbol")
                df = df.with_columns((ema_fast - ema_slow).alias(macd_col))

            if sig_col not in df.columns:
                df = df.with_columns(
                    pl.col(macd_col).ewm_mean(span=sig).over("symbol").alias(sig_col)
                )

            if hist_col not in df.columns:
                df = df.with_columns((pl.col(macd_col) - pl.col(sig_col)).alias(hist_col))

            return df, col_name

        elif ind == "BOLLINGER":
            period = item.period
            std = item.std_multiplier if item.std_multiplier is not None else 2.0

            mid_col = f"BB_Mid_{period}_{std}"
            upper_col = f"BB_Upper_{period}_{std}"
            lower_col = f"BB_Lower_{period}_{std}"

            if (
                mid_col not in df.columns
                or upper_col not in df.columns
                or lower_col not in df.columns
            ):
                sma_expr = pl.col("close").rolling_mean(window_size=period).over("symbol")
                std_expr = pl.col("close").rolling_std(window_size=period).over("symbol")
                df = df.with_columns(
                    [
                        sma_expr.alias(mid_col),
                        (sma_expr + std * std_expr).alias(upper_col),
                        (sma_expr - std * std_expr).alias(lower_col),
                    ]
                )

            return df, col_name

        else:
            raise ValueError(f"Unsupported indicator: {ind}")

    def evaluate(
        self,
        df: pl.DataFrame,
        conditions: List[ScreeningCondition],
        logic: str = "AND",
    ) -> List[str]:
        """Evaluate a list of screening conditions across symbols.

        Args:
            df: Input OHLC DataFrame with at least 'symbol', 'date', 'close'.
            conditions: List of screening conditions.
            logic: 'AND' (all conditions must match) or 'OR' (at least one must match).

        Returns:
            Sorted list of symbol strings that match the screening criteria.
        """
        if df.is_empty() or not conditions:
            return []

        # Ensure ordered by symbol and date
        df = df.sort(["symbol", "date"])
        input_columns = df.columns

        cond_boolean_cols: List[str] = []

        for idx, cond in enumerate(conditions):
            # Compute LHS column
            df, lhs_col = self.compute_indicator_column(df, cond)

            if cond.reference is not None:
                # Compute RHS column from reference
                df, rhs_col = self.compute_indicator_column(df, cond.reference)
                rhs_expr = pl.col(rhs_col)
                null_guard = pl.col(lhs_col).is_not_null() & pl.col(rhs_col).is_not_null()
            else:
                # Scalar value comparison
                rhs_expr = pl.lit(cond.value)
                null_guard = pl.col(lhs_col).is_not_null()

            op = cond.operator
            if op == "<":
                comp_expr = pl.col(lhs_col) < rhs_expr
            elif op == "<=":
                comp_expr = pl.col(lhs_col) <= rhs_expr
            elif op == ">":
                comp_expr = pl.col(lhs_col) > rhs_expr
            elif op == ">=":
                comp_expr = pl.col(lhs_col) >= rhs_expr
            elif op == "==":
                comp_expr = pl.col(lhs_col) == rhs_expr
            elif op == "!=":
                comp_expr = pl.col(lhs_col) != rhs_expr
            else:
                raise ValueError(f"Unsupported operator: {op}")

            # Safe boolean result: False if any operand is null
            bool_col_name = f"__cond_{idx}__"
            cond_expr = (
                pl.when(null_guard & comp_expr).then(True).otherwise(False).alias(bool_col_name)
            )
            df = df.with_columns(cond_expr)
            cond_boolean_cols.append(bool_col_name)

            # Retain only derived columns that a later condition can reuse.
            # This bounds memory for requests containing many different MACD/BB windows.
            future_columns = set()
            for remaining in conditions[idx + 1 :]:
                future_columns.add(self.get_column_identifier(remaining)[0])
                if remaining.reference is not None:
                    future_columns.add(self.get_column_identifier(remaining.reference)[0])
            keep = (
                input_columns
                + cond_boolean_cols
                + [column for column in sorted(future_columns) if column in df.columns]
            )
            df = df.select(list(dict.fromkeys(keep)))

        # Select the latest available trading row independently per symbol
        latest_df = df.group_by("symbol", maintain_order=True).last()

        # Combine conditions using requested logic
        if logic.upper() == "AND":
            match_expr = pl.all_horizontal([pl.col(c) for c in cond_boolean_cols])
        elif logic.upper() == "OR":
            match_expr = pl.any_horizontal([pl.col(c) for c in cond_boolean_cols])
        else:
            raise ValueError(f"Unsupported logic: {logic}")

        matched_symbols = (
            latest_df.filter(match_expr).select("symbol").sort("symbol")["symbol"].to_list()
        )

        return matched_symbols
