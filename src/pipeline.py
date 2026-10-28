
import os
import logging

import pandas as pd
import requests
import psycopg
from dotenv import load_dotenv
from psycopg import sql
from psycopg.types.json import Jsonb

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

CITIES = {
    "Bandung": (-6.9175, 107.6191),
    "Jakarta": (-6.2088, 106.8456),
    "Surabaya": (-7.2575, 112.7521),
}


def extract_weather(city, latitude, longitude):
    url = "https://historical-forecast-api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "wind_speed_10m"
        ),
        "forecast_days": 1,
        "timezone": "Asia/Bangkok",
    }

    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()

    payload = response.json()
    hourly = payload["hourly"]

    df = pd.DataFrame({
        "city": city,
        "observed_at": hourly["time"],
        "temperature_c": hourly["temperature_2m"],
        "humidity_pct": hourly["relative_humidity_2m"],
        "wind_speed_kmh": hourly["wind_speed_10m"],
    })

    df["observed_at"] = pd.to_datetime(
        df["observed_at"], errors="coerce"
    )

    df = df.dropna(subset=["observed_at"])

    numeric_columns = [
        "temperature_c",
        "humidity_pct",
        "wind_speed_kmh",
    ]

    df[numeric_columns] = df[numeric_columns].apply(
        pd.to_numeric, errors="coerce"
    )

    df = df.drop_duplicates(
        subset=["city", "observed_at"]
    )

    if df["humidity_pct"].dropna().gt(100).any() or \
       df["humidity_pct"].dropna().lt(0).any():
        raise ValueError(f"Invalid humidity data for {city}")

    if df.empty:
        raise ValueError(f"No valid weather data for {city}")

    # Simpan respons mentah untuk audit dan debugging.
    os.makedirs("data/raw", exist_ok=True)

    with open(f"data/raw/{city.lower()}_raw.json", "w", encoding="utf-8") as f:
        import json
        json.dump(payload, f, ensure_ascii=False, indent=2)

    logging.info("%s: extracted %s rows", city, len(df))
    return df


def load_weather(df):
    connection_config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.environ["DB_NAME"],
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
    }

    rows = [
        (
            row.city,
            row.observed_at.to_pydatetime(),
            None if pd.isna(row.temperature_c) else float(row.temperature_c),
            None if pd.isna(row.humidity_pct) else float(row.humidity_pct),
            None if pd.isna(row.wind_speed_kmh) else float(row.wind_speed_kmh),
        )
        for row in df.itertuples(index=False)
    ]

    query = """
        INSERT INTO weather_observations (
            city, observed_at, temperature_c,
            humidity_pct, wind_speed_kmh
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (city, observed_at)
        DO UPDATE SET
            temperature_c = EXCLUDED.temperature_c,
            humidity_pct = EXCLUDED.humidity_pct,
            wind_speed_kmh = EXCLUDED.wind_speed_kmh,
            loaded_at = CURRENT_TIMESTAMP;
    """

    with psycopg.connect(**connection_config) as conn:
        with conn.cursor() as cur:
            cur.executemany(query, rows)

    logging.info("Loaded %s rows", len(rows))


def main():
    all_data = []

    for city, (latitude, longitude) in CITIES.items():
        df = extract_weather(city, latitude, longitude)
        all_data.append(df)

    combined = pd.concat(all_data, ignore_index=True)
    load_weather(combined)

    logging.info(
        "Pipeline completed: %s rows processed",
        len(combined)
    )


if __name__ == "__main__":
    main()
