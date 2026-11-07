# gpt-image Image Generation & Editing Skill

*Read this in other languages: [日本語](./README.ja-JP.md)*

A [Claude Code](https://claude.com/claude-code) **Agent Skill** that generates **and edits** images using Azure AI Foundry (Microsoft Foundry) image models — `gpt-image-2`, `gpt-image-2.5-flare`, and `gpt-image-2.5-sunburst` — and saves them locally. It supports text-to-image generation (`images/generations`) as well as image editing (`images/edits`): single-image edits, multi-image merge (object replacement), and mask-based inpainting.

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
- **Model selection** — `gpt-image-2` (default), `gpt-image-2.5-flare` (fast, everyday quality), `gpt-image-2.5-sunburst` (highest precision), each with its own deployment
- Full parameter control: `size`, `quality`, `output_format`, `background`, `output_compression`, `n`, `user` (`complexity` and markup-guided edits are implemented but currently rejected by Azure, so they are disabled)
- Pre-flight validation (size constraints, parameter dependencies, and — for editing — input image count/existence/type/extension and PNG mask) before any API call
- Keyless **Microsoft Entra ID** authentication (preferred) with **API key** fallback
- `.env` support for credentials **and** default parameters
- Automatic, unique, title-based filenames saved to `./images` by default

---

## Requirements

- An Azure subscription with an Azure OpenAI (Foundry) resource.
- At least one deployed model: `gpt-image-2`, `gpt-image-2.5-flare`, or `gpt-image-2.5-sunburst`.
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
cp -r .claude/skills/gpt-image ~/.claude/skills/

# Install Python dependencies
pip install -r ~/.claude/skills/gpt-image/requirements.txt
```

**Windows (PowerShell)**

```powershell
# From the root of this repository
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
Copy-Item -Recurse -Force ".claude\skills\gpt-image" "$env:USERPROFILE\.claude\skills\"

# Install Python dependencies
pip install -r "$env:USERPROFILE\.claude\skills\gpt-image\requirements.txt"
```

After copying, the skill lives at:

- macOS / Linux: `~/.claude/skills/gpt-image/`
- Windows: `C:\Users\<you>\.claude\skills\gpt-image\`

Start (or restart) Claude Code and confirm the `gpt-image` skill is listed. A request like *"画像を生成して"* / *"generate an image of ..."* will load it automatically.

### Per-project installation

Keep the skill under the project's `.claude/skills/gpt-image/` (as in this repository). It is then available only within that project. Install the dependencies the same way:

```bash
pip install -r .claude/skills/gpt-image/requirements.txt
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
| `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2` / `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE` / `AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST` | ✅* | Deployment name per model. The one matching the selected model is used |
| `AZURE_OPENAI_DEPLOYMENT` | ✅* | Fallback deployment name when the per-model variable is not set |
| `AZURE_OPENAI_API_KEY` | — | Only for API key auth. If omitted, keyless Entra ID auth is used |
| `AZURE_OPENAI_API_VERSION` | — | Defaults to `2025-04-01-preview` (`preview` when `AZURE_OPENAI_API_STYLE=v1`) |
| `AZURE_OPENAI_API_STYLE` | — | Endpoint style: `deployments` (default) or `v1` (`/openai/v1/images/...`) |
| `AZURE_OPENAI_TOKEN_SCOPE` | — | Entra ID token scope. Defaults to `https://cognitiveservices.azure.com/.default` |

\* Set either the per-model variable or `AZURE_OPENAI_DEPLOYMENT`.

To use both 2.5 models side by side, deploy both and set one variable per model:

```dotenv
GPT_IMAGE_MODEL=gpt-image-2.5-flare
AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_FLARE=<your-flare-deployment>
AZURE_OPENAI_DEPLOYMENT_GPT_IMAGE_2_5_SUNBURST=<your-sunburst-deployment>
```

Then switch per call with `--model gpt-image-2.5-sunburst`.

### 4. Default parameters via `.env` (key feature)

You can set your **preferred default values** for every generation parameter in `.env`. This means you can configure, once, the size/quality/format you usually want — and then just say *"generate an image of X"* without repeating flags every time.

**Precedence: CLI argument > `.env` (environment variable) > built-in default.**

| Parameter | Environment variable | Built-in default | Allowed values |
|-----------|----------------------|------------------|----------------|
| model | `GPT_IMAGE_MODEL` | `gpt-image-2` | `gpt-image-2` / `gpt-image-2.5-flare` / `gpt-image-2.5-sunburst` |
| size | `GPT_IMAGE_SIZE` | `1024x1024` | `WxH` (see size constraints) |
| quality | `GPT_IMAGE_QUALITY` | `high` | `low` / `medium` / `high` (2.5 models also `xhigh` / `max` / `auto`) |
| output format | `GPT_IMAGE_FORMAT` | `png` | `png` / `jpeg` (WEBP not supported) |
| background | `GPT_IMAGE_BACKGROUND` | `auto` | `auto` / `transparent` (2.5 models also `opaque`; transparent requires `png`) |
| complexity | `GPT_IMAGE_COMPLEXITY` | (none) | `low` / `medium` / `high` (2.5 models only; currently unavailable on Azure) |
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
| `--model` | `GPT_IMAGE_MODEL` | `gpt-image-2`/`gpt-image-2.5-flare`/`gpt-image-2.5-sunburst` | `gpt-image-2` | Must match the deployment it resolves to |
| `--quality` | `GPT_IMAGE_QUALITY` | `low`/`medium`/`high` (+ `xhigh`/`max`/`auto` on 2.5) | `high` | `low` for low latency. 2.5's `high` uses fewer tokens than gpt-image-2's `high` |
| `--format` | `GPT_IMAGE_FORMAT` | `png`/`jpeg` | `png` | WEBP is not available on Azure yet |
| `--background` | `GPT_IMAGE_BACKGROUND` | `auto`/`transparent` (+ `opaque` on 2.5) | `auto` | `transparent` requires `--format png` |
| `--compression` | `GPT_IMAGE_COMPRESSION` | `0`–`100` | `100` | JPEG only |
| `--complexity` | `GPT_IMAGE_COMPLEXITY` | `low`/`medium`/`high` | (none) | 2.5 models only. **Currently unavailable on Azure** (rejected as an unknown parameter) |
| `--n` | `GPT_IMAGE_N` | `1`–`10` | `1` | Number of images |
| `--user` | `GPT_IMAGE_USER` | any string | (optional) | Usage-tracking ID |
| `--output` | `GPT_IMAGE_OUTPUT_DIR` | directory path | `./images` | Created if missing |

### Size constraints (all models)

On the 2.5 models, sizes above 2560x1440 total pixels are experimental; the script prints a warning and continues.

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
| `--mask` | (none) | transparent PNG path | (optional) | Edit region (transparent area only). Must be PNG. Cannot be combined with `--markup` |
| `--markup` | (none) | transparent PNG path | (optional) | 2.5 models only. **Currently unavailable on Azure** (rejected as an unknown parameter). Use `--mask` instead |
| `--model` / `--complexity` | `GPT_IMAGE_MODEL` / `GPT_IMAGE_COMPLEXITY` | as for generation | as for generation | |
| `--size` | `GPT_IMAGE_EDIT_SIZE` | `WxH` or `auto` | `auto` | `auto` matches the input image; `WxH` uses the same constraints as generation |
| `--quality` | `GPT_IMAGE_QUALITY` | as for generation (depends on model) | `high` | |
| `--format` | `GPT_IMAGE_FORMAT` | `png`/`jpeg` | `png` | |
| `--background` | `GPT_IMAGE_BACKGROUND` | as for generation (depends on model) | `auto` | `transparent` requires `--format png` |
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
cd .claude/skills/gpt-image
python -m pytest -q
```

The test suite covers validation, authentication resolution, storage/naming, the API client (with mocked HTTP) for both generation and editing, multi-image merge / mask handling, edit input validation, `.env` loading, parameter-default precedence, and CLI orchestration for both `generate_image.py` and `edit_image.py`.

This project was built with a Kiro-style spec-driven workflow; the specification lives under `.kiro/specs/gpt-image-2-skill/`.

---

## License

Licensed under the [MIT License](./LICENSE).
