from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "processed" / "mvp_dataset" / "deployment_static_validation.json"


def main() -> None:
    dockerfile_path = ROOT / "Dockerfile"
    compose_path = ROOT / "docker-compose.yml"
    env_example_path = ROOT / ".env.example"

    checks: dict[str, bool] = {
        "dockerfile_exists": dockerfile_path.exists(),
        "compose_exists": compose_path.exists(),
        "env_example_exists": env_example_path.exists(),
    }

    compose = (
        yaml.safe_load(compose_path.read_text(encoding="utf-8")) if compose_path.exists() else {}
    )
    services = compose.get("services", {}) if isinstance(compose, dict) else {}
    checks["compose_has_api_mysql_redis"] = {"api", "mysql", "redis"}.issubset(services)
    checks["all_services_have_healthcheck"] = all(
        isinstance(services.get(name), dict) and "healthcheck" in services[name]
        for name in ("api", "mysql", "redis")
    )

    dockerfile = dockerfile_path.read_text(encoding="utf-8") if dockerfile_path.exists() else ""
    env_example = env_example_path.read_text(encoding="utf-8") if env_example_path.exists() else ""
    # 只检查常见真实密钥形态；示例中的 change-me 占位符不属于真实秘密。
    secret_patterns = [r"sk-[A-Za-z0-9_-]{20,}", r"Bearer\s+[A-Za-z0-9_-]{20,}"]
    checks["dockerfile_has_no_embedded_api_key"] = not any(
        re.search(pattern, dockerfile, re.IGNORECASE) for pattern in secret_patterns
    )
    checks["env_example_has_no_embedded_api_key"] = not any(
        re.search(pattern, env_example, re.IGNORECASE) for pattern in secret_patterns
    )
    checks["dockerfile_has_healthcheck"] = "HEALTHCHECK" in dockerfile
    checks["compose_api_uses_persistent_volume"] = "finagent_data:/app/data" in str(
        services.get("api", {}).get("volumes", [])
    )
    checks["compose_runs_api_with_mysql_and_redis"] = (
        services.get("api", {}).get("environment", {}).get("FINANCE_BACKEND") == "mysql"
        and services.get("api", {}).get("environment", {}).get("REDIS_URL")
        == "redis://redis:6379/0"
    )

    result = {
        "status": "STATIC_PASS" if all(checks.values()) else "STATIC_FAIL",
        "scope": "Dockerfile/Compose static validation",
        "docker_runtime_available": None,
        "services": sorted(services),
        "checks": checks,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "STATIC_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
