import asyncio
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from newsintel.adapters.http.safe_fetcher import FetchRequest, FetchResult, SafeHttpFetcher


class RobotsDeniedError(PermissionError):
    """Raised when robots policy disallows a crawler request."""


class RobotsUnavailableError(RuntimeError):
    """Raised when robots policy cannot be obtained and fail-closed mode is enabled."""


@dataclass(frozen=True, slots=True)
class RobotsRule:
    allow: bool
    pattern: str

    @property
    def specificity(self) -> int:
        return len(self.pattern.replace("*", "").removesuffix("$"))


@dataclass(frozen=True, slots=True)
class RobotsPolicy:
    groups: tuple[tuple[tuple[str, ...], tuple[RobotsRule, ...]], ...]

    @classmethod
    def allow_all(cls) -> "RobotsPolicy":
        return cls(groups=((('*',), ()),))

    @classmethod
    def disallow_all(cls) -> "RobotsPolicy":
        return cls(groups=((('*',), (RobotsRule(allow=False, pattern='/'),)),))

    @classmethod
    def parse(cls, payload: str | bytes) -> "RobotsPolicy":
        text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
        groups: list[tuple[tuple[str, ...], tuple[RobotsRule, ...]]] = []
        agents: list[str] = []
        rules: list[RobotsRule] = []
        saw_rule = False

        def flush() -> None:
            nonlocal agents, rules, saw_rule
            if agents:
                groups.append((tuple(dict.fromkeys(agents)), tuple(rules)))
            agents = []
            rules = []
            saw_rule = False

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            directive = key.strip().casefold()
            value = value.strip()
            if directive == "user-agent":
                if saw_rule:
                    flush()
                if value:
                    agents.append(value.casefold())
                continue
            if directive not in {"allow", "disallow"} or not agents:
                continue
            saw_rule = True
            if directive == "disallow" and not value:
                continue
            rules.append(RobotsRule(allow=directive == "allow", pattern=value))
        flush()
        return cls(groups=tuple(groups))

    def is_allowed(self, url: str, *, user_agent: str) -> bool:
        parsed = urlsplit(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        rules = self._rules_for_user_agent(user_agent)
        best: RobotsRule | None = None
        for rule in rules:
            if not _robots_pattern_matches(rule.pattern, path):
                continue
            if best is None:
                best = rule
                continue
            if rule.specificity > best.specificity:
                best = rule
            elif rule.specificity == best.specificity and rule.allow and not best.allow:
                best = rule
        return True if best is None else best.allow

    def _rules_for_user_agent(self, user_agent: str) -> tuple[RobotsRule, ...]:
        token = _product_token(user_agent)
        specific: list[RobotsRule] = []
        wildcard: list[RobotsRule] = []
        for agents, rules in self.groups:
            if any(agent != "*" and _agent_matches(agent, token) for agent in agents):
                specific.extend(rules)
            elif "*" in agents:
                wildcard.extend(rules)
        return tuple(specific if specific else wildcard)


@dataclass(frozen=True, slots=True)
class _CachedRobots:
    policy: RobotsPolicy
    expires_at: datetime


class HostRequestBudget:
    """Process-local per-host concurrency and minimum-spacing budget."""

    def __init__(
        self,
        *,
        max_concurrent_per_host: int = 2,
        min_interval_seconds: float = 0.25,
    ) -> None:
        if max_concurrent_per_host < 1:
            raise ValueError("max_concurrent_per_host must be positive")
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")
        self._max_concurrent = max_concurrent_per_host
        self._min_interval = min_interval_seconds
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._spacing_locks: dict[str, asyncio.Lock] = {}
        self._next_allowed: dict[str, float] = {}
        self._registry_lock = asyncio.Lock()

    async def _state_for_host(self, host: str) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        async with self._registry_lock:
            semaphore = self._semaphores.setdefault(
                host,
                asyncio.Semaphore(self._max_concurrent),
            )
            spacing_lock = self._spacing_locks.setdefault(host, asyncio.Lock())
            return semaphore, spacing_lock

    @asynccontextmanager
    async def slot(self, url: str) -> AsyncIterator[None]:
        host = (urlsplit(url).hostname or "").casefold()
        semaphore, spacing_lock = await self._state_for_host(host)
        async with semaphore:
            async with spacing_lock:
                now = time.monotonic()
                wait_for = max(0.0, self._next_allowed.get(host, 0.0) - now)
                if wait_for:
                    await asyncio.sleep(wait_for)
                self._next_allowed[host] = time.monotonic() + self._min_interval
            yield


class CrawlPolicyHttpFetcher:
    """Robots-aware fetcher that also applies a process-local per-host request budget."""

    def __init__(
        self,
        inner: SafeHttpFetcher,
        *,
        user_agent: str,
        robots_enabled: bool = True,
        robots_cache_seconds: int = 3_600,
        fail_closed_on_robots_error: bool = True,
        max_concurrent_per_host: int = 2,
        min_host_interval_seconds: float = 0.25,
    ) -> None:
        self._inner = inner
        self._user_agent = user_agent
        self._robots_enabled = robots_enabled
        self._robots_cache_seconds = robots_cache_seconds
        self._fail_closed = fail_closed_on_robots_error
        self._robots_cache: dict[str, _CachedRobots] = {}
        self._robots_locks: dict[str, asyncio.Lock] = {}
        self._cache_registry_lock = asyncio.Lock()
        self._budget = HostRequestBudget(
            max_concurrent_per_host=max_concurrent_per_host,
            min_interval_seconds=min_host_interval_seconds,
        )

    async def fetch(self, request: FetchRequest) -> FetchResult:
        if self._robots_enabled and not _is_robots_url(request.url):
            policy = await self._robots_policy_for(request.url, allowed_domains=request.allowed_domains)
            if not policy.is_allowed(request.url, user_agent=self._user_agent):
                raise RobotsDeniedError(f"robots policy disallows URL: {request.url}")
        async with self._budget.slot(request.url):
            return await self._inner.fetch(request)

    async def _robots_policy_for(
        self,
        url: str,
        *,
        allowed_domains: tuple[str, ...] | None = None,
    ) -> RobotsPolicy:
        origin = _origin(url)
        now = datetime.now(UTC)
        cached = self._robots_cache.get(origin)
        if cached is not None and cached.expires_at > now:
            return cached.policy

        lock = await self._robots_lock(origin)
        async with lock:
            now = datetime.now(UTC)
            cached = self._robots_cache.get(origin)
            if cached is not None and cached.expires_at > now:
                return cached.policy
            robots_url = f"{origin}/robots.txt"
            try:
                result = await self._inner.fetch(FetchRequest(url=robots_url, allowed_domains=allowed_domains))
            except Exception as exc:
                if self._fail_closed:
                    raise RobotsUnavailableError(
                        f"robots policy unavailable for {origin}: {type(exc).__name__}"
                    ) from exc
                policy = RobotsPolicy.allow_all()
            else:
                if 200 <= result.status_code < 300:
                    policy = RobotsPolicy.parse(result.body)
                elif result.status_code == 429 or result.status_code >= 500:
                    if self._fail_closed:
                        raise RobotsUnavailableError(
                            f"robots policy unavailable for {origin}: HTTP {result.status_code}"
                        )
                    policy = RobotsPolicy.allow_all()
                else:
                    policy = RobotsPolicy.allow_all()
            self._robots_cache[origin] = _CachedRobots(
                policy=policy,
                expires_at=now + timedelta(seconds=self._robots_cache_seconds),
            )
            return policy

    async def _robots_lock(self, origin: str) -> asyncio.Lock:
        async with self._cache_registry_lock:
            return self._robots_locks.setdefault(origin, asyncio.Lock())


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def _is_robots_url(url: str) -> bool:
    return urlsplit(url).path.casefold() == "/robots.txt"


def _product_token(user_agent: str) -> str:
    first = user_agent.strip().split(maxsplit=1)[0]
    return first.split("/", 1)[0].casefold()


def _agent_matches(agent: str, product_token: str) -> bool:
    normalized = agent.strip().casefold()
    return bool(normalized) and (
        normalized == product_token or product_token.startswith(normalized)
    )


def _robots_pattern_matches(pattern: str, path: str) -> bool:
    if not pattern:
        return False
    anchored_end = pattern.endswith("$")
    raw = pattern[:-1] if anchored_end else pattern
    expression = "^" + re.escape(raw).replace(r"\*", ".*")
    if anchored_end:
        expression += "$"
    return re.search(expression, path) is not None
