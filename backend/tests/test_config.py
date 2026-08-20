"""Settings derived from the environment."""


def test_a_providers_bare_postgres_url_picks_the_driver_we_install():
    """Neon/Render/Heroku all emit `postgresql://`, which SQLAlchemy resolves to
    psycopg2. We depend on psycopg3, so a verbatim paste must still connect."""
    from app.config import _normalise_db_url

    assert _normalise_db_url(
        "postgresql://u:p@ep-x.aws.neon.tech/neondb?sslmode=require"
    ) == "postgresql+psycopg://u:p@ep-x.aws.neon.tech/neondb?sslmode=require"
    assert _normalise_db_url("postgres://u:p@h/d").startswith("postgresql+psycopg://")
    # Already-explicit and non-postgres URLs are left exactly as given.
    assert _normalise_db_url("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert _normalise_db_url("sqlite:///./dev.db") == "sqlite:///./dev.db"
