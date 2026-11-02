# Codoc

Codoc is a local Python CLI for one documentation site in a git repo. This checkout is the tool package. This slice installs the `codoc` command. Every command is a stub.

## Install the command

From this directory, create a virtual environment and install the package in editable mode.

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Run the stubs

`codoc` with no arguments prints help and exits 0. `codoc --help` does the same. Help lists every command.

```bash
codoc
codoc generate
codoc drift
```

`codoc generate` prints `codoc generate: not implemented` to stderr and exits 2.

`codoc drift` prints `codoc validate: not implemented` to stderr and exits 2.

`python -m codoc` calls the same `main` function. The program name stays `codoc`.

## Read the plan

Product decisions live in the Project store. Read these files before changing behavior.

- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/product-plan.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/product-plan.md)
- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/repo-layout.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/repo-layout.md)
- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/tickets-sketch.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/tickets-sketch.md)
- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/project-context.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/project-context.md)
- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/open-questions.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/docs/open-questions.md)
- [`/Users/ahmedsabry/Library/Application Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/preferences.md`](file:///Users/ahmedsabry/Library/Application%20Support/Cursor/AgentStores/cursor_agent_stores/bc-a5e789be-6cc1-4c4a-adb5-025dfe673a0f/files/preferences.md)
