CREATE TABLE IF NOT EXISTS weather_observations (
    city VARCHAR(100) NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    temperature_c DOUBLE PRECISION,
    humidity_pct DOUBLE PRECISION,
    wind_speed_kmh DOUBLE PRECISION,
    loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (city, observed_at),

    CHECK (
        humidity_pct IS NULL
        OR humidity_pct BETWEEN 0 AND 100
    )
);