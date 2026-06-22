# gpt-image-2 Image Generation & Editing Skill

*Read this in other languages: [日本語](./README.ja-JP.md)*

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that generates **and edits** images using the Azure AI Foundry (Microsoft Foundry) `gpt-image-2` model and saves them locally. It supports text-to-image generation (`images/generations`) as well as image editing (`images/edits`): single-image edits, multi-image merge (object replacement), and mask-based inpainting.

The skill follows two core principles:

1. **Claude never hand-writes the API call.** All generation/editing logic (request building, validation, saving) lives in self-contained Python scripts. Claude only invokes them as documented in `SKILL.md`.
2. **Parameters are passed as validated CLI arguments with sensible defaults.** For generation only `--prompt` is required; for editing `--prompt` and at least one `--image` are required. Everything else falls back to a default that you can customize through a `.env` file.

---

## Features

- Text-to-image generation via Azure OpenAI `images/generations`
- **Image editing via Azure OpenAI `images/edits`:**
  - **Single-image edit** — modify an existing image with a prompt
  - **Multi-image merge** — pass several images to composite them (replace an object in the base image with an object from another image)
  - **Mask-based inpainting** — limit edits to the transparent region of a PNG mask
- Full parameter control: `size`, `quality`, `output_format`, `background`, `output_compression`, `n`, `user`
- Pre-flight validation (size constraints, parameter dependencies, and — for editing — input image count/existence/type/extension and PNG mask) before any API call
- Keyless **Microsoft Entra ID** authentication (preferred) with **API key** fallback
- `.env` support for credentials **and** default parameters
- Automatic, unique, title-based filenames saved to `./images` by default

---

## Requirements

- An Azure subscription with an Azure OpenAI (Foundry) resource.
- A deployed `gpt-image-2` model. The gpt-image family requires [limited access registration](https://aka.ms/oai/access).
- API version `2025-04-01-preview` or later (older versions such as `2024-02-01` do **not** support gpt-image-2).
- Python 3.10+ with the dependencies in `requirements.txt` (`requests`, `azure-identity`).

---

## Installation

The skill is a self-contained directory (`SKILL.md`, `scripts/`, `requirements.txt`). You can install it **globally** (available in every project) or **per-project**.

### Global installation (recommended)

Copy the skill into your personal Claude Code skills directory (`~/.claude/skills/`). Skills placed there are available in every Claude Code session, regardless of which project you open.

**macOS / Linux**

```bash
# From the root of this repository
mkdir -p ~/.claude/skills
cp -r .claude/skills/gpt-image-2 ~/.claude/skills/

# Install Python dependencies
pip install -r ~/.claude/skills/gpt-image-2/requirements.txt
```

**Windows (PowerShell)**

```powershell
# From the root of this repository
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".claude\skills\gpt-image-2" "$env:USERPROFILE\.claude\skills\"

# Install Python dependencies
pip install -r "$env:USERPROFILE\.claude\skills\gpt-image-2\requirements.txt"
```

After copying, the skill lives at:

- macOS / Linux: `~/.claude/skills/gpt-image-2/`
- Windows: `C:\Users\<you>\.claude\skills\gpt-image-2\`

Start (or restart) Claude Code and confirm the `gpt-image-2` skill is listed. A request like *"画像を生成して"* / *"generate an image of ..."* will load it automatically.

### Per-project installation

Keep the skill under the project's `.claude/skills/gpt-image-2/` (as in this repository). It is then available only within that project. Install the dependencies the same way:

```bash
pip install -r .claude/skills/gpt-image-2/requirements.txt
```

---

## Configuration via `.env`

Credentials and default parameters are read from **environment variables**. For convenience, the skill can load them from a `.env` file so you don't have to export variables manually.

### 1. Create your `.env` from the template

```bash
# From your project root
cp .env.example .env      # macOS / Linux
# Copy-Item .env.example .env   # Windows PowerShell
```

Then edit `.env` and fill in your Azure values.

> **Security:** `.env` contains secrets. Never commit or share it. This repository's `.gitignore` already excludes `.env` (while keeping `.env.example`).

### 2. How `.env` is discovered and applied

- When the skill runs, it searches for a `.env` file **starting from the current working directory and walking up** the directory tree, using the first one it finds. Place `.env` at your project root.
- **OS environment variables always take precedence.** `.env` only fills in variables that are not already set in your shell.
- Because discovery is relative to where you run Claude Code (not where the skill is installed), for a **globally installed** skill you should either:
  - put a `.env` in each project where you use it, or
  - set the variables as OS-level environment variables, or
  - place a single `.env` in a parent directory that covers your projects.

### 3. Azure connection variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_OPENAI_ENDPOINT` | ✅ | Resource base URL, e.g. `https://<resource>.openai.azure.com` (no deployment/path) |
| `AZURE_OPENAI_DEPLOYMENT` | ✅ | The deployment name you gave `gpt-image-2` |
| `AZURE_OPENAI_API_KEY` | — | Only for API key auth. If omitted, keyless Entra ID auth is used |
| `AZURE_OPENAI_API_VERSION` | — | Defaults to `2025-04-01-preview` |

### 4. Default parameters via `.env` (key feature)

You can set your **preferred default values** for every generation parameter in `.env`. This means you can configure, once, the size/quality/format you usually want — and then just say *"generate an image of X"* without repeating flags every time.

**Precedence: CLI argument > `.env` (environment variable) > built-in default.**

| Parameter | Environment variable | Built-in default | Allowed values |
|-----------|----------------------|------------------|----------------|
| size | `GPT_IMAGE_SIZE` | `1024x1024` | `WxH` (see size constraints) |
| quality | `GPT_IMAGE_QUALITY` | `high` | `low` / `medium` / `high` |
| output format | `GPT_IMAGE_FORMAT` | `png` | `png` / `jpeg` (WEBP not supported) |
| background | `GPT_IMAGE_BACKGROUND` | `auto` | `auto` / `transparent` (transparent requires `png`) |
| compression | `GPT_IMAGE_COMPRESSION` | `100` | `0`–`100` (JPEG only) |
| count | `GPT_IMAGE_N` | `1` | `1`–`10` |
| output dir | `GPT_IMAGE_OUTPUT_DIR` | `./images` | any directory path (created if missing) |
| user id | `GPT_IMAGE_USER` | (none) | any string |

Example `.env` defaults section:

```dotenv
# Always produce landscape, high-quality PNGs into ./assets
GPT_IMAGE_SIZE=1536x1024
GPT_IMAGE_QUALITY=high
GPT_IMAGE_FORMAT=png
GPT_IMAGE_OUTPUT_DIR=./assets
```

With the above, `python scripts/generate_image.py --prompt "a fox"` produces a 1536×1024 high-quality PNG in `./assets` — no extra flags needed. Passing `--size 1024x1024` on the command line would still override the `.env` value for that one run.

See [`.env.example`](./.env.example) for the fully annotated template.

---

## Usage

### Through Claude Code

Just ask in natural language, e.g. *"Azure で水彩画風の富士山の画像を作って"*. Claude loads the skill and runs the script, then reports the saved file path(s).

### Direct CLI

```bash
python scripts/generate_image.py --prompt "A serene Japanese garden, watercolor style"
```

On success, the absolute path of each saved file is printed to stdout (one per line).

#### Examples

```bash
# Default square PNG into ./images
python scripts/generate_image.py --prompt "桜並木の通学路、アニメ風"

# Transparent PNG (logos / icons)
python scripts/generate_image.py --prompt "a minimal mountain logo" --background transparent --format png

# Compressed landscape JPEG
python scripts/generate_image.py --prompt "coastal road, photographic" --size 1536x1024 --format jpeg --compression 80

# Multiple images into a custom folder
python scripts/generate_image.py --prompt "cat character concepts" --n 4 --output ./out
```

### Parameters

| Argument | Env override | Values | Default | Notes |
|----------|--------------|--------|---------|-------|
| `--prompt` | (none) | any text | **required** | Generation instruction |
| `--size` | `GPT_IMAGE_SIZE` | `WxH` | `1024x1024` | Recommended: `1024x1024`, `1536x1024`, `1024x1536` |
| `--quality` | `GPT_IMAGE_QUALITY` | `low`/`medium`/`high` | `high` | `low` for low latency |
| `--format` | `GPT_IMAGE_FORMAT` | `png`/`jpeg` | `png` | WEBP not supported on Azure |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto`/`transparent` | `auto` | `transparent` requires `--format png` |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG only |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | Number of images |
| `--user` | `GPT_IMAGE_USER` | any string | (optional) | Usage-tracking ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | directory path | `./images` | Created if missing |

### Size constraints (gpt-image-2)

`--size` must satisfy **all** of the following, or the script errors out before calling the API:

- Both edges are multiples of **16 px**
- Long edge ≤ **3840 px**
- Aspect ratio ≤ **3:1**
- Total pixel count between **655,360** and **8,294,400**

### Output & file naming

- Default output directory is `./images` (created automatically if missing).
- Files are named `<title>_<timestamp>_<index>.<ext>`, where `<title>` is derived from the prompt (filesystem-illegal characters removed, truncated). Multiple images (`--n > 1`) are numbered sequentially.

---

## Image editing

Edit existing images with a prompt using `scripts/edit_image.py` (the `images/edits` endpoint). It shares the same authentication, `.env` handling, validation, and saving logic as generation. `--prompt` and at least one `--image` are required.

There are two modes:

1. **Single-image edit** — pass one `--image` and describe the change in the prompt (recolor, add/remove objects, restyle, replace background).
2. **Multi-image merge (object replacement)** — pass multiple `--image` arguments. The **first image is the base**; the rest are reference material. You can replace an object in the base image with an object from another image. Add a `--mask` (a transparent PNG the same size as the base) to limit the edit to the masked (transparent) region only (inpainting).

```bash
# Single-image edit (replace the background)
python scripts/edit_image.py --prompt "change the sky to a sunset" --image ./images/landscape.png

# Mask-based inpainting (edit only the transparent region of the mask)
python scripts/edit_image.py --prompt "replace the hat with a red beret" --image ./photo.png --mask ./hat_mask.png

# Multi-image merge: replace an object in the base with an object from the second image
python scripts/edit_image.py \
  --prompt "replace the bag the person is holding with the red backpack from the second image" \
  --image ./base.png \
  --image ./red_backpack.png \
  --mask ./bag_region.png
```

On success, the absolute path of each saved file is printed to stdout, using the same naming rules as generation.

### Editing parameters

| Argument | Env override | Values | Default | Notes |
|----------|--------------|--------|---------|-------|
| `--prompt` | (none) | any text | **required** | Editing instruction |
| `--image` | (none) | image path (repeatable) | **required (≥1)** | Input image(s); multiple = merge. First is the base. `png`/`jpg`/`jpeg`/`webp`, up to 16 |
| `--mask` | (none) | transparent PNG path | (optional) | Edit region (transparent area only). Must be PNG |
| `--size` | `GPT_IMAGE_EDIT_SIZE` | `WxH` or `auto` | `auto` | `auto` matches the input image; `WxH` uses the same constraints as generation |
| `--quality` | `GPT_IMAGE_QUALITY` | `low`/`medium`/`high` | `high` | |
| `--format` | `GPT_IMAGE_FORMAT` | `png`/`jpeg` | `png` | |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto`/`transparent` | `auto` | `transparent` requires `--format png` |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG only |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | Number of images |
| `--user` | `GPT_IMAGE_USER` | any string | (optional) | Usage-tracking ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | directory path | `./images` | Created if missing |

---

## Authentication

1. **Microsoft Entra ID (keyless, preferred).** Uses `DefaultAzureCredential`. Run `az login` locally, or rely on a Managed Identity in the cloud. No long-lived key is stored.
2. **API key (fallback).** If Entra ID is unavailable and `AZURE_OPENAI_API_KEY` is set, the key is used via the `api-key` header.

Secrets are read from environment variables / `.env` only, are never hard-coded in `SKILL.md` or the scripts, and are never written to stdout, stderr, or logs.

---

## Development

```bash
cd .claude/skills/gpt-image-2
python -m pytest -q
```

The test suite covers validation, authentication resolution, storage/naming, the API client (with mocked HTTP) for both generation and editing, multi-image merge / mask handling, edit input validation, `.env` loading, parameter-default precedence, and CLI orchestration for both `generate_image.py` and `edit_image.py`.

This project was built with a Kiro-style spec-driven workflow; the specification lives under `.kiro/specs/gpt-image-2-skill/`.

---

## License

Licensed under the [MIT License](./LICENSE).
