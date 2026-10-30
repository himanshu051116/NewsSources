from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_local_configuration_templates_use_consistent_ports() -> None:
    env_example = (ROOT / ".env.example").read_text()
    readme = (ROOT / "README.md").read_text()
    compose = (ROOT / "compose.yaml").read_text()

    assert "localhost:5434/newsintel" in env_example
    assert "localhost:6380/0" in env_example
    assert "http://localhost:9010" in env_example
    assert "127.0.0.1:8010" in readme
    assert "127.0.0.1:8000" not in readme
    assert '"127.0.0.1:6333:6333"' in compose
    assert '"127.0.0.1:6334:6334"' in compose


def test_example_environment_contains_no_real_provider_keys() -> None:
    env_example = (ROOT / ".env.example").read_text()

    for variable in (
        "NEWSINTEL_GUARDIAN_API_KEY",
        "NEWSINTEL_NEW_YORK_TIMES_API_KEY",
        "NEWSINTEL_NEWS_API_KEY",
        "NEWSINTEL_GOOGLE_FACT_CHECK_API_KEY",
    ):
        assert f"{variable}=\n" in env_example
