from pathlib import Path

import pandas as pd

from src.data.utils import load_config, logger


PROCESSED_DIR = Path("data/processed")
PANEL_PATH = PROCESSED_DIR / "uniswap_v3_panel_4pools.parquet"
DAILY_OUTPUT_PATH = PROCESSED_DIR / "pools_daily.csv"
HOURLY_SAMPLE_OUTPUT_PATH = PROCESSED_DIR / "pools_hourly_subsample.csv"
HOURLY_SAMPLE_INTERVAL = 6

DAILY_REQUIRED_COLUMNS = {
    "datetime",
    "pool_name",
    "open_clean",
    "high_clean",
    "low_clean",
    "close_clean",
    "volumeUSD",
    "feesUSD",
    "tvlUSD",
    "txCount",
}


def export_requested_csvs() -> None:
    """Export daily rollups and a six-hourly sample from the processed hourly panel."""
    if not PANEL_PATH.exists():
        raise FileNotFoundError(
            f"Không tìm thấy {PANEL_PATH}. Hãy chạy "
            "`python -m src.data.build_dataset` trước."
        )

    config = load_config()
    start = pd.Timestamp(config["timeframe"]["start_date"])
    end = pd.Timestamp(config["timeframe"]["end_date"])

    panel = pd.read_parquet(PANEL_PATH)
    missing_columns = sorted(DAILY_REQUIRED_COLUMNS.difference(panel.columns))
    if missing_columns:
        raise ValueError(
            f"Panel thiếu cột cần thiết để export: {', '.join(missing_columns)}"
        )

    panel["datetime"] = pd.to_datetime(panel["datetime"], utc=True)
    panel = panel.loc[panel["datetime"].between(start, end)].copy()
    if panel.empty:
        raise ValueError(
            f"Không có dữ liệu trong khoảng {start} đến {end}. "
            "Hãy cập nhật dữ liệu nguồn và chạy lại build_dataset."
        )

    panel = panel.sort_values(["pool_name", "datetime"]).reset_index(drop=True)
    panel["_date"] = panel["datetime"].dt.floor("D")

    daily = (
        panel.groupby(["pool_name", "_date"], as_index=False, sort=True)
        .agg(
            open=("open_clean", "first"),
            high=("high_clean", "max"),
            low=("low_clean", "min"),
            close=("close_clean", "last"),
            volumeUSD=("volumeUSD", "sum"),
            feesUSD=("feesUSD", "sum"),
            tvlUSD=("tvlUSD", "last"),
            txCount=("txCount", "sum"),
            hours_observed=("datetime", "size"),
        )
        .rename(columns={"_date": "datetime"})
    )
    daily["is_complete_day"] = daily["hours_observed"].eq(24)
    daily.to_csv(DAILY_OUTPUT_PATH, index=False)

    hourly_sample = panel.loc[
        panel["datetime"].dt.hour.mod(HOURLY_SAMPLE_INTERVAL).eq(0)
    ].drop(columns="_date")
    hourly_sample.to_csv(HOURLY_SAMPLE_OUTPUT_PATH, index=False)

    incomplete_days = int((~daily["is_complete_day"]).sum())
    logger.info(
        "Đã xuất %s (%s dòng) và %s (%s dòng). "
        "Ngày không đủ 24 giờ quan sát: %s.",
        DAILY_OUTPUT_PATH,
        len(daily),
        HOURLY_SAMPLE_OUTPUT_PATH,
        len(hourly_sample),
        incomplete_days,
    )


if __name__ == "__main__":
    export_requested_csvs()
