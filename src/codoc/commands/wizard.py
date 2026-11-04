"""Interactive TTY prompts for `codoc init` (no separate setup command)."""

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from codoc.config import EngineConfig, LlmConfig, PathsConfig, ProjectConfig, ValeConfig

_LLM_PROVIDERS = (
    "none",
    "openai",
    "anthropic",
    "openai-compatible",
    "cursor-cli",
)
_ENGINES = ("zensical", "mkdocs")

PromptFn = Callable[[str], str]


class WizardError(Exception):
    """Invalid wizard input."""


@dataclass(frozen=True, slots=True)
class WizardDefaults:
    engine_name: str = "zensical"
    site_name: str = "Documentation"
    vale_enabled: bool = True
    terms: tuple[str, ...] = ()
    llm_provider: str | None = None
    llm_model: str | None = None
    rewrite_stubs: bool = False


def defaults_from_config(config: ProjectConfig) -> WizardDefaults:
    """Seed wizard answers from an existing project config."""
    return WizardDefaults(
        engine_name=config.engine.name,
        site_name=config.engine.site_name,
        vale_enabled=config.vale.enabled,
        terms=config.terms,
        llm_provider=config.llm.provider,
        llm_model=config.llm.model,
        rewrite_stubs=config.llm.rewrite_stubs,
    )


def default_project_config(*, site_name: str | None = None) -> ProjectConfig:
    """Non-interactive `--yes` defaults (Zensical + Vale, no LLM)."""
    engine = EngineConfig(site_name=site_name or "Documentation")
    return ProjectConfig(engine=engine)


def apply_wizard_defaults(
    base: ProjectConfig,
    choices: WizardDefaults,
) -> ProjectConfig:
    """Merge wizard choices into a ProjectConfig, keeping paths/ignore/theme/nav."""
    engine = EngineConfig(
        name=choices.engine_name,
        docs_dir=base.engine.docs_dir,
        site_dir=base.engine.site_dir,
        site_name=choices.site_name,
        theme=base.engine.theme,
        nav=base.engine.nav,
    )
    llm = LlmConfig(
        provider=choices.llm_provider,
        model=choices.llm_model,
        rewrite_stubs=choices.rewrite_stubs,
        embedding_model=base.llm.embedding_model,
    )
    paths = base.paths if base.paths.scripts_dir else PathsConfig()
    return ProjectConfig(
        engine=engine,
        vale=ValeConfig(choices.vale_enabled),
        llm=llm,
        paths=paths,
        terms=choices.terms,
        ignore_dirs=base.ignore_dirs,
    )


def run_wizard(
    defaults: WizardDefaults,
    *,
    prompt: PromptFn | None = None,
) -> WizardDefaults:
    """
    Ask for engine, Vale, terms, and optional LLM settings.

    `prompt` is injectable for tests (receives the full prompt string).
    """
    ask = prompt if prompt is not None else _default_prompt

    engine = _choose(
        ask,
        "Docs engine",
        _ENGINES,
        defaults.engine_name if defaults.engine_name in _ENGINES else "zensical",
    )
    site_name = _ask_text(ask, "Site name", defaults.site_name)
    vale_enabled = _ask_bool(ask, "Enable Vale spellcheck", defaults.vale_enabled)
    terms_default = ", ".join(defaults.terms)
    terms_raw = _ask_text(ask, "Seed terms (comma-separated)", terms_default)
    terms = tuple(part.strip() for part in terms_raw.split(",") if part.strip())

    provider_label = defaults.llm_provider or "none"
    provider = _choose(ask, "LLM provider", _LLM_PROVIDERS, provider_label)
    llm_provider: str | None
    llm_model: str | None
    rewrite_stubs = False
    if provider == "none":
        llm_provider = None
        llm_model = None
    else:
        llm_provider = provider
        model_default = defaults.llm_model or _default_model(provider)
        llm_model = _ask_text(ask, "LLM model", model_default)
        rewrite_stubs = _ask_bool(
            ask,
            "Rewrite eligible manual stubs on generate",
            defaults.rewrite_stubs,
        )

    return WizardDefaults(
        engine_name=engine,
        site_name=site_name,
        vale_enabled=vale_enabled,
        terms=terms,
        llm_provider=llm_provider,
        llm_model=llm_model,
        rewrite_stubs=rewrite_stubs,
    )


def confirm(message: str, *, default: bool = False, prompt: PromptFn | None = None) -> bool:
    """Yes/no confirmation for re-init update/merge."""
    ask = prompt if prompt is not None else _default_prompt
    return _ask_bool(ask, message, default)


def is_interactive_tty() -> bool:
    """True when stdin and stdout are TTYs (wizard is allowed)."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def site_name_from_root(root: Path) -> str:
    """Humanize the repo directory name for engine.site_name."""
    name = root.name.replace("-", " ").replace("_", " ").strip()
    return name.title() if name else "Documentation"


def _default_prompt(message: str) -> str:
    sys.stdout.write(message)
    sys.stdout.flush()
    return sys.stdin.readline()


def _default_model(provider: str) -> str:
    if provider == "anthropic":
        return "claude-sonnet-4-5"
    if provider == "cursor-cli":
        return "composer-2"
    if provider == "openai-compatible":
        return "local-model"
    return "gpt-4.1"


def _choose(ask: PromptFn, label: str, options: tuple[str, ...], default: str) -> str:
    joined = "/".join(options)
    raw = ask(f"{label} [{joined}] (default {default}): ").strip().lower()
    if raw == "":
        return default
    if raw in options:
        return raw
    if raw.isdigit():
        index = int(raw) - 1
        if 0 <= index < len(options):
            return options[index]
    raise WizardError(f"invalid {label.lower()} {raw!r}")


def _ask_text(ask: PromptFn, label: str, default: str) -> str:
    suffix = f" (default {default!r})" if default else ""
    raw = ask(f"{label}{suffix}: ")
    text = raw.strip()
    return text if text else default


def _ask_bool(ask: PromptFn, label: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = ask(f"{label} [{hint}]: ").strip().lower()
    if raw == "":
        return default
    if raw in {"y", "yes"}:
        return True
    if raw in {"n", "no"}:
        return False
    raise WizardError(f"expected y or n, got {raw!r}")
