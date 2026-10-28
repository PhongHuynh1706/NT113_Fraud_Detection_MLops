
import numpy as np
import pandas as pd


TARGET = "is_fraud"
DATETIME_COLUMN = "transaction_datetime"

NUMERIC_FEATURES = [
    "transaction_amount",
    "transaction_hour",
    "customer_age",
    "account_age_days",
    "credit_limit",
    "credit_score",
    "num_cards_held",
    "transactions_last_1h",
    "transactions_last_24h",
    "transactions_last_7d",
    "amount_last_1h",
    "amount_last_24h",
    "days_since_last_transaction",
    "distance_from_home_km",
    "distance_from_last_tx_km",
    "amount_vs_avg_ratio",
    "avg_transaction_amount_30d",
    "std_transaction_amount_30d",
    "num_declined_last_30d",
    "num_chargebacks_ever",
]

CATEGORICAL_FEATURES = [
    "merchant_category",
    "merchant_country",
    "transaction_day_of_week",
    "customer_gender",
    "customer_state",
    "transaction_channel",
    "device_type",
    "browser",
    "email_domain",
]

BINARY_FEATURES = [
    "card_present",
    "international_transaction",
    "high_risk_country",
    "used_chip",
    "used_pin",
    "is_weekend",
]

FEATURE_COLUMNS = (
    NUMERIC_FEATURES
    + CATEGORICAL_FEATURES
    + BINARY_FEATURES
)


def load_dataset(path):
    df = pd.read_csv(path, low_memory=False)

    required_columns = set(
        FEATURE_COLUMNS + [TARGET, DATETIME_COLUMN]
    )

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df[DATETIME_COLUMN] = pd.to_datetime(
        df[DATETIME_COLUMN],
        errors="raise"
    )

    if df[DATETIME_COLUMN].isna().any():
        raise ValueError("Missing transaction timestamps")

    if df[TARGET].isna().any():
        raise ValueError("Missing fraud labels")

    df[TARGET] = pd.to_numeric(
        df[TARGET], errors="raise"
    )

    if not df[TARGET].isin([0, 1]).all():
        raise ValueError("is_fraud must be 0 or 1")

    df[TARGET] = df[TARGET].astype(int)

    return df.sort_values(
        DATETIME_COLUMN, kind="stable"
    ).reset_index(drop=True)


def split_dataset(
    df,
    train_ratio=0.70,
    validation_ratio=0.15
):
    n = len(df)

    train_end = int(n * train_ratio)
    val_end = int(
        n * (train_ratio + validation_ratio)
    )

    if not (0 < train_end < val_end < n):
        raise ValueError("Invalid dataset split sizes")

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    for name, subset in [
        ("train", train_df),
        ("validation", val_df),
        ("test", test_df)
    ]:
        if subset[TARGET].nunique() != 2:
            raise ValueError(
                f"{name} must contain both fraud classes"
            )

    return train_df, val_df, test_df


def fit_preprocessing(train_df):
    medians = {}

    for column in NUMERIC_FEATURES:
        values = pd.to_numeric(
            train_df[column], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)

        median = values.median()

        if pd.isna(median):
            raise ValueError(
                f"No valid values for {column}"
            )

        medians[column] = float(median)

    return {"numeric_medians": medians}


def transform_features(df, preprocessing):
    X = df[FEATURE_COLUMNS].copy()

    for column in NUMERIC_FEATURES:
        X[column] = (
            pd.to_numeric(X[column], errors="coerce")
            .replace([np.inf, -np.inf], np.nan)
            .fillna(
                preprocessing["numeric_medians"][column]
            )
            .astype(float)
        )

    for column in CATEGORICAL_FEATURES:
        X[column] = (
            X[column]
            .fillna("__MISSING__")
            .astype(str)
        )

    for column in BINARY_FEATURES:
        values = pd.to_numeric(
            X[column], errors="coerce"
        )

        if not values.dropna().isin([0, 1]).all():
            raise ValueError(
                f"Invalid binary feature: {column}"
            )

        X[column] = values.fillna(-1).astype(int)

    return X
