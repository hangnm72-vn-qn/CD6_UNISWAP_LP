import sys
from pathlib import Path
import numpy as np
import pandas as pd

# Đường dẫn thư mục
PROCESSED_DIR = Path("data/processed")

REQUIRED_COLUMNS = [
    "datetime", "pool_name", "price", "open_clean", "high_clean", "low_clean", "close_clean",
    "volumeUSD", "feesUSD", "tvlUSD", "log_return", "vol_hist_24h", "vol_garch_forecast",
    "volume_turnover", "fee_yield", "cost_rebalance_usd"
]


def audit_parquet_file(file_path: Path):
    print(f"\n{'='*20} KIỂM TRA FILE: {file_path.name} {'='*20}")
    
    if not file_path.exists():
        print(f"[THẤT BẠI] File không tồn tại: {file_path}")
        return False

    df = pd.read_parquet(file_path)
    passed = True
    total_rows = len(df)
    print(f"1. Tổng số dòng quan sát: {total_rows:,} rows")

    # 1. Kiểm tra Schema
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        print(f"❌ [LỖI SCHEMA] Thiếu các cột bắt buộc: {missing_cols}")
        passed = False
    else:
        print("✅ [ĐẠT] Schema đầy đủ toàn bộ các cột cốt lõi.")

    # 2. Kiểm tra tính đơn điệu của thời gian
    if "datetime" not in df.columns:
        pass
    elif not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
        print("❌ [LỖI DTYPE] Cột 'datetime' không đúng định dạng timestamp!")
        passed = False
    else:
        if df["datetime"].isna().any():
            print("❌ [LỖI THỜI GIAN] Cột datetime chứa giá trị thiếu/NaT.")
            passed = False

        if "pool_name" in df.columns:
            time_groups = df.groupby("pool_name", dropna=False, sort=False)
            monotonic = time_groups["datetime"].apply(lambda values: values.is_monotonic_increasing)
            duplicate_counts = time_groups["datetime"].apply(lambda values: int(values.duplicated().sum()))
            failed_pools = monotonic[~monotonic].index.tolist()
            duplicate_pools = duplicate_counts[duplicate_counts > 0].to_dict()
            if failed_pools:
                print(f"❌ [LỖI THỜI GIAN] datetime không tăng dần trong pool: {failed_pools}")
                passed = False
            if duplicate_pools:
                print(f"❌ [LỖI THỜI GIAN] Mốc datetime trùng trong pool: {duplicate_pools}")
                passed = False
            if not failed_pools and not duplicate_pools:
                print("✅ [ĐẠT] datetime tăng dần nghiêm ngặt và duy nhất trong từng pool.")
        else:
            if not df["datetime"].is_monotonic_increasing:
                print("❌ [LỖI THỜI GIAN] Dữ liệu thời gian KHÔNG tăng dần đơn điệu!")
                passed = False
            if df["datetime"].duplicated().any():
                dup_count = int(df["datetime"].duplicated().sum())
                print(f"❌ [LỖI THỜI GIAN] Phát hiện {dup_count} mốc thời gian bị trùng lặp!")
                passed = False
            if df["datetime"].is_monotonic_increasing and not df["datetime"].duplicated().any():
                start_time = df["datetime"].iloc[0]
                end_time = df["datetime"].iloc[-1]
                print(f"✅ [ĐẠT] Trục thời gian tăng dần: từ {start_time} đến {end_time}.")

    # 3. Kiểm tra tính liên tục (Gap detection)
    if "datetime" in df.columns and pd.api.types.is_datetime64_any_dtype(df["datetime"]):
        time_groups = (
            df.groupby("pool_name", dropna=False, sort=False)
            if "pool_name" in df.columns else [(None, df)]
        )
        group_gaps = {}
        expected_step = pd.Timedelta(hours=1)
        for pool_name, group in time_groups:
            gaps = group["datetime"].sort_values().diff().dropna()
            gaps = gaps[gaps > expected_step]
            if not gaps.empty:
                group_gaps[pool_name] = (len(gaps), gaps.max())
        if group_gaps:
            print(f"⚠️ [CẢNH BÁO] Khoảng trống thời gian > 1 giờ theo pool: {group_gaps}")
        else:
            print("✅ [ĐẠT] Lưới thời gian liên tục từng giờ trong từng pool.")

    # 4. Kiểm tra Giá trị phi lý (Sanity Check)
    sanity_passed = True
    if "close_clean" in df.columns:
        close = pd.to_numeric(df["close_clean"], errors="coerce")
        invalid_price = int((close.isna() | ~np.isfinite(close) | (close <= 0)).sum())
        if invalid_price:
            print(f"❌ [LỖI GIÁ] Có {invalid_price} dòng giá thiếu, không hữu hạn hoặc <= 0!")
            passed = False
            sanity_passed = False
    for column, label in [("tvlUSD", "TVL"), ("volumeUSD", "Volume")]:
        if column in df.columns:
            values = pd.to_numeric(df[column], errors="coerce")
            invalid_values = int((~np.isfinite(values) | (values < 0)).sum())
            if invalid_values:
                print(f"❌ [LỖI GIÁ TRỊ] Có {invalid_values} dòng {label} âm hoặc không hữu hạn!")
                passed = False
                sanity_passed = False
    if sanity_passed and all(column in df.columns for column in ["close_clean", "tvlUSD", "volumeUSD"]):
        print("✅ [ĐẠT] Price > 0, TVL >= 0, Volume >= 0 và các giá trị hữu hạn.")

    nonfinite_columns = []
    for column in ["log_return", "vol_garch_forecast", "cost_rebalance_usd"]:
        if column in df.columns:
            values = pd.to_numeric(df[column], errors="coerce")
            count = int((~np.isfinite(values)).sum())
            if count:
                nonfinite_columns.append((column, count))
    if nonfinite_columns:
        print(f"❌ [LỖI FEATURE] Có giá trị không hữu hạn: {nonfinite_columns}")
        passed = False

    # 5. Kiểm tra Tỷ lệ Missing (NaN)
    print("\n--- Báo cáo Tỷ lệ Missing theo Cột ---")
    existing_required = [col for col in REQUIRED_COLUMNS if col in df.columns]
    nan_summary = df[existing_required].isna().mean()
    high_nan_cols = nan_summary[nan_summary > 0.05]
    if not high_nan_cols.empty:
        print(f"⚠️ [CHÚ Ý] Các cột có tỷ lệ NaN > 5%:\n{high_nan_cols}")
    else:
        print("✅ [ĐẠT] Tỷ lệ Missing ở tất cả các cột đều < 5% (hoặc chỉ NaN ở đầu chuỗi rolling).")

    # 6. Tóm tắt phân phối tài chính (Quick Distribution)
    print("\n--- Tóm tắt Phân phối (Quantiles) ---")
    metrics_to_show = ["close_clean", "vol_hist_24h", "vol_garch_forecast", "volume_turnover", "cost_rebalance_usd"]
    metrics_existing = [m for m in metrics_to_show if m in df.columns]
    stats = df[metrics_existing].describe(percentiles=[0.05, 0.5, 0.95]).T[["min", "5%", "50%", "95%", "max"]]
    print(stats.to_string())

    print("✅ Kết quả kiểm định: ĐẠT" if passed else "❌ Kết quả kiểm định: KHÔNG ĐẠT")
    return passed


def run_all_audits():
    parquet_files = list(PROCESSED_DIR.glob("*.parquet"))
    if not parquet_files:
        print("Không tìm thấy file .parquet nào trong thư mục data/processed/!")
        return False

    all_passed = True
    for p_file in parquet_files:
        all_passed = audit_parquet_file(p_file) and all_passed
    return all_passed


if __name__ == "__main__":
    raise SystemExit(0 if run_all_audits() else 1)