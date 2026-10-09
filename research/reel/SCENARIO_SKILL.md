---
name: scenario-api-mcp
description: Use Scenario through the direct HTTP API or through Scenario MCP. Use when the user asks about Scenario, AI image generation, video generation, image editing, upscaling, background removal, 3D generation, or asset workflows in code or chat.
---

# Scenario API + MCP

Scenario can be used in two different ways:

- **Scenario API** for product code, scripts, backend services, and batch jobs
- **Scenario MCP** for interactive use inside Cursor or other MCP clients

They expose the same model catalog, but the calling shape is different.

## Which one to use

| Interface | Best for | How it works |
|-----------|----------|--------------|
| **Scenario MCP** | Interactive asset generation in chat, prompt iteration, model discovery, showing assets inline | Call MCP tools like `recommend`, `get_model_schema`, `run_model`, `display_asset` |
| **Scenario API** | Shipping features, automation, batch processing, server-side code, scripts | Send authenticated HTTP requests to `https://api.cloud.scenario.com/v1` |

Rule of thumb:

- Use **MCP** when the agent is helping a human generate or review assets in-session
- Use **API** when code needs to generate, edit, upload, or manage assets directly

## Core difference: parameter shape

This is the most important distinction.

### Scenario API

Model-specific inputs go directly in the JSON body:

```json
{
  "prompt": "a frontier carpenter portrait",
  "aspectRatio": "3:4",
  "size": "2K"
}
```

### Scenario MCP

Model-specific inputs go inside `parameters`:

```json
{
  "model_id": "model_bytedance-seedream-4-5",
  "parameters": {
    "prompt": "a frontier carpenter portrait",
    "aspectRatio": "3:4",
    "size": "2K"
  }
}
```

**Important:** if you pass `prompt`, `aspectRatio`, `image`, `referenceImages`, etc. at the top level to `run_model`, the request can fail with errors like `Input prompt is required` because the model never receives those fields.

## Scenario MCP

Scenario MCP is the interactive tool layer. Use it when working inside Cursor or another MCP-enabled client.

### Typical MCP workflow

1. **Discover workspace**
   - `list_teams`
   - `list_projects`
2. **Pick a model**
   - `recommend` for model suggestions
   - `search` to find a specific model or tool
3. **Inspect the schema**
   - `get_model_schema`
4. **Run the model**
   - `run_model`
5. **Show the result**
   - `display_asset`
6. **Follow up if needed**
   - `manage_jobs`
   - `manage_assets`
   - `upload_asset`

### MCP tools to know

| Tool | Purpose |
|------|---------|
| `list_teams` | Discover available Scenario teams |
| `list_projects` | Discover projects within a team |
| `recommend` | Ask Scenario which model to use |
| `search` | Find models, assets, or workflows |
| `get_model_schema` | Get the exact accepted inputs for a model |
| `run_model` | Generate or transform content |
| `display_asset` | Show an image/video/audio/3D asset inline |
| `manage_jobs` | Poll or cancel long-running jobs |
| `manage_assets` | Inspect, tag, download, or organize assets |
| `upload_asset` | Upload an image/audio/video/3D file for use as input |

### Required MCP pattern

Always do this before generation:

1. Call `get_model_schema`
2. Read the exact parameter names and allowed values
3. Call `run_model` with those fields nested under `parameters`

### MCP example: get schema, then generate

```json
{
  "model_id": "model_bytedance-seedream-4-5"
}
```

Seedream 4.5 currently accepts:

- `prompt`
- `referenceImages`
- `aspectRatio`
- `size`
- `sequentialImageGeneration`
- `maxImages`

Then call `run_model` like this:

```json
{
  "model_id": "model_bytedance-seedream-4-5",
  "parameters": {
    "prompt": "Stylized male carpenter character reference, age 42, sturdy frontier builder, single portrait, warm golden light.",
    "aspectRatio": "3:4",
    "size": "2K",
    "sequentialImageGeneration": "disabled",
    "maxImages": 1
  },
  "wait": true,
  "team_id": "team_abc123",
  "project_id": "proj_xyz789"
}
```

Then show the output:

```json
{
  "asset_id": "asset_img001",
  "format": "display",
  "team_id": "team_abc123",
  "project_id": "proj_xyz789"
}
```

### MCP example: use reference images

If the schema includes `image`, `images`, or `referenceImages`, upload the file first and pass the returned `asset_id`.

```json
{
  "model_id": "model_google-gemini-pro-image-editing",
  "parameters": {
    "referenceImages": ["asset_ref001"],
    "prompt": "Make the clothing more rugged and frontier practical",
    "aspectRatio": "3:4",
    "resolution": "2K"
  }
}
```

### MCP gotchas

- **Always** call `get_model_schema` first. Different models use different field names.
- In `run_model`, model inputs belong under **`parameters`**.
- If the user belongs to multiple teams or projects, include both `team_id` and `project_id`.
- For file parameters, pass a Scenario `asset_id`, not a local path.
- Use `display_asset` to show the result inline. Do not rely on raw asset metadata calls for presentation.
- If `wait: true` takes too long, use `manage_jobs` to poll the `job_id`.


### Character sheet prompt template

```text
Character design reference image for <character name>, stylized <gender> <role>, age <age>. Show the same character in one image with three fully rendered colored views arranged in this exact order: full-body front view on the left, full-body side view in the middle, and large face close-up on the right. All three views must be complete illustrated renders of the same character, not silhouettes, not shadow figures, not outline turnarounds, not placeholder shapes. Neutral light background, no text, no labels, no extra characters.

<1-2 sentences of personality and surface read>

<face and expression details>

<hair and grooming details>

<body type, clothing, props, and silhouette details>

Keep the same proportions, same clothing, same colors, and same identity across all three views.

<desired game style prompt>

### Prompt length note for Seedream 4.5

In practice, Seedream 4.5 rejects overly long prompts. Keep the prompt concise
enough to stay within the model's current limit.

If you hit a prompt-length error:

- compress prose
- remove repeated descriptors
- keep the stable style block short
- prioritize role, face, clothing, and silhouette over extra mood language

## Scenario API

Use the HTTP API when writing code or automation.

## Authentication & setup

All requests use **Basic Auth** with API key + secret.

### Step 1: Get credentials

Your API key and secret will be provided to you by the team organizer. **Do not create your own key.**

Once you have the credentials, add them to a `.env` file in the project root:

```bash
VITE_SCENARIO_API_KEY=your_api_key_here
VITE_SCENARIO_API_SECRET=your_api_secret_here
```

A template is also available at `.claude/skills/scenario-api/.env.example`.

**Important:** The `.env` file is in `.gitignore` - never commit API keys to the repo.

### Step 2: Build auth headers

```typescript
const apiKey = process.env.SCENARIO_API_KEY;
const apiSecret = process.env.SCENARIO_API_SECRET;
const credentials = btoa(`${apiKey}:${apiSecret}`);

const headers = {
  Authorization: `Basic ${credentials}`,
  "Content-Type": "application/json",
};
```

```python
import os
import requests
from requests.auth import HTTPBasicAuth

auth = HTTPBasicAuth(
    os.environ["SCENARIO_API_KEY"],
    os.environ["SCENARIO_API_SECRET"],
)
```

## Base URL

```text
https://api.cloud.scenario.com/v1
```

## Core endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/generate/custom/{modelId}` | POST | Generate images, videos, 3D, audio, and transformations |
| `/generate/remove-background` | POST | Remove image background |
| `/jobs/{jobId}` | GET | Poll job status |
| `/jobs/{jobId}/action` | POST | Cancel a job |
| `/assets/{assetId}` | GET | Fetch asset metadata or URL |
| `/assets` | POST | Upload an asset |

## API generation pattern

All generation follows the same pattern:

1. `POST` to `/generate/custom/{modelId}` with model-specific params
2. Receive `{ job: { jobId, status } }`
3. Poll `/jobs/{jobId}` until `status` is `success` or `failure`
4. On success, read `job.metadata.assetIds`
5. Fetch the asset URL via `/assets/{assetId}`

### Important: parameters are model-specific

**Every model has its own set of parameters.** When the user switches models or when building UI with multiple model options, you MUST:

1. Look up the exact parameters for each model
2. Adapt the payload dynamically based on the selected model
3. Validate allowed values before sending the request

Examples:

- Gemini uses `resolution: "2K"` while some other models use `size` or `1 MP`
- Some models use `image`, others use `images`, `referenceImages`, `startImage`, or `firstFrameImage`
- Aspect ratio values differ by model
- Duration can be `number` or `string` depending on the model

### TypeScript example

```typescript
const BASE = "https://api.cloud.scenario.com/v1";

async function generate(modelId: string, payload: Record<string, unknown>): Promise<string> {
  const res = await fetch(`${BASE}/generate/custom/${modelId}`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(await res.text());
  }

  const data = await res.json();
  return data.job.jobId;
}

async function pollJob(jobId: string): Promise<string[]> {
  while (true) {
    const res = await fetch(`${BASE}/jobs/${jobId}`, { headers });
    const { job } = await res.json();

    if (job.status === "success") {
      return job.metadata.assetIds;
    }

    if (job.status === "failure" || job.status === "canceled") {
      throw new Error(`Job ${job.status}`);
    }

    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
}

async function getAssetUrl(assetId: string): Promise<string> {
  const res = await fetch(`${BASE}/assets/${assetId}`, { headers });
  const data = await res.json();
  return data.asset.url;
}
```

### Python example

```python
import time
import requests

BASE = "https://api.cloud.scenario.com/v1"

def generate(model_id, payload):
    r = requests.post(f"{BASE}/generate/custom/{model_id}", json=payload, auth=auth)
    r.raise_for_status()
    return r.json()["job"]["jobId"]

def poll_job(job_id):
    while True:
        r = requests.get(f"{BASE}/jobs/{job_id}", auth=auth)
        job = r.json()["job"]
        if job["status"] == "success":
            return job["metadata"]["assetIds"]
        if job["status"] in ("failure", "canceled"):
            raise Exception(f"Job {job['status']}")
        time.sleep(3)
```

## Asset upload

### API upload

Upload base64 data directly:

```typescript
async function uploadAsset(base64Content: string, name: string): Promise<string> {
  const res = await fetch(`${BASE}/assets`, {
    method: "POST",
    headers,
    body: JSON.stringify({ image: base64Content, name }),
  });

  const data = await res.json();
  return data.asset.id;
}
```

### MCP upload

Use `upload_asset`, then pass the returned `asset_id` into `run_model.parameters`.

## Recommended default models

When no specific model is requested, use these defaults:

| Category | Model | ID |
|----------|-------|----|
| Image Generation | Gemini 3.0 Pro | `model_google-gemini-pro-image-t2i` |
| Image Editing | Gemini 3.0 Pro Edit | `model_google-gemini-pro-image-editing` |
| Video (I2V) | Kling V3 I2V Pro | `model_kling-v3-i2v-pro` |
| Video (T2V) | Kling V3 T2V Pro | `model_kling-v3-t2v-pro` |
| Upscaling | Scenario Flux Upscale | `model_sc-upscale-flux` |
| Background Removal | Photoroom | `model_photoroom-background-removal` |
| 3D Generation | Tripo 3.0 Image to 3D | `model_tripo-v3-0-image-to-3d` |
| Lipsync | Kling Lipsync | `model_kling-lip-sync` |

## Common capability examples

The same model IDs work in both the API and MCP. The difference is only whether the model-specific fields go directly in the HTTP body or inside MCP `parameters`.

### 1. Text-to-image

| Model | ID | Key features |
|-------|----|-------------|
| Gemini 3.0 Pro | `model_google-gemini-pro-image-t2i` | 1K-4K resolution, Google Search |
| Flux 2 Max | `model_bfl-flux-2-max` | Up to 4MP, reference images |
| Flux 2 Pro | `model_bfl-flux-2-pro` | Prompt upsampling |
| GPT Image 1.5 | `model_openai-gpt-image-1-5` | Up to 10 outputs, transparent BG |
| Seedream 4.5 | `model_bytedance-seedream-4-5` | Up to 4K, sequential generation |
| Imagen 4 | `model_imagen4` | Simple, high quality |

API example:

```typescript
generate("model_google-gemini-pro-image-t2i", {
  prompt: "A futuristic city at sunset",
  aspectRatio: "16:9",
  resolution: "2K",
});
```

MCP example:

```json
{
  "model_id": "model_google-gemini-pro-image-t2i",
  "parameters": {
    "prompt": "A futuristic city at sunset",
    "aspectRatio": "16:9",
    "resolution": "2K"
  }
}
```

### 2. Image editing

Editing models usually require `referenceImages`.

```typescript
generate("model_google-gemini-pro-image-editing", {
  referenceImages: ["asset_xxx"],
  prompt: "Change the sky to a dramatic sunset",
  aspectRatio: "16:9",
  resolution: "2K",
});
```

### 3. Video generation

```typescript
generate("model_kling-v3-t2v-pro", {
  prompt: "A cat playing piano, cinematic",
  aspectRatio: "16:9",
  duration: 5,
});

generate("model_kling-v3-i2v-pro", {
  prompt: "The character starts walking forward",
  image: "asset_xxx",
  duration: 5,
});
```

### 4. Image upscaling

```typescript
generate("model_sc-upscale-flux", {
  image: "asset_xxx",
  upscaleFactor: 4,
  preset: "balanced",
});
```

### 5. Background removal

```typescript
fetch(`${BASE}/generate/remove-background`, {
  method: "POST",
  headers,
  body: JSON.stringify({ image: "asset_xxx", format: "png" }),
});

generate("model_photoroom-background-removal", { image: "asset_xxx" });
```

### 6. 3D generation

```typescript
generate("model_tripo-v3-0-image-to-3d", {
  image: "asset_xxx",
  texture: true,
  textureQuality: "detailed",
  pbr: true,
  faceLimit: 30000,
});
```

### 7. Lipsync

```typescript
generate("model_kling-lip-sync", {
  videoUrl: "asset_xxx",
  text: "Hello, welcome to our demo",
  voiceId: "en_AOT",
});
```

## Common parameters reference

Most models share these parameter concepts, but the exact names and allowed values vary:

| Parameter | Type | Description |
|-----------|------|-------------|
| `prompt` | string | Text description |
| `referenceImages` | assetId[] | Input images for editing models |
| `image` | assetId | Single input image |
| `aspectRatio` | string | Output ratio |
| `resolution` / `size` | string | Output quality |
| `duration` | number or string | Video duration |
| `numOutputs` / `maxImages` | number | Number of generated outputs |
| `seed` | number | Reproducibility |
| `guidanceScale` | number | Prompt adherence |
| `negativePrompt` | string | What to avoid |
| `generateAudio` | boolean | Generate audio with video |

## Error handling

- **429 Too Many Requests** - implement exponential backoff
- **403 Access denied** - check model access and API plan
- **404 Model not found** - verify model ID
- Parse error JSON fields like `{ message, reason }`

## Fetching the model catalog

The model list updates frequently. Fetch the live catalog using the **public auth token**:

```bash
curl -s -H "Authorization: public-auth-token" \
  "https://api.cloud.scenario.com/v1/models" | jq '.models | length'
```

### Useful queries

```bash
# List all public models with id, name, type
curl -s -H "Authorization: public-auth-token" \
  "https://api.cloud.scenario.com/v1/models" | \
  jq '.models[] | select(.privacy == "public") | {id, name, type}'

# Find models by name
curl -s -H "Authorization: public-auth-token" \
  "https://api.cloud.scenario.com/v1/models" | \
  jq '.models[] | select(.name | test("gemini"; "i")) | {id, name, type}'

# Get model details including parameters
curl -s -H "Authorization: public-auth-token" \
  "https://api.cloud.scenario.com/v1/models" | \
  jq '.models[] | select(.id == "model_google-gemini-pro-image-t2i")'
```

### TypeScript example

```typescript
async function fetchModels(): Promise<Model[]> {
  const res = await fetch("https://api.cloud.scenario.com/v1/models", {
    headers: { Authorization: "public-auth-token" },
  });

  const data = await res.json();
  return data.models;
}
```

## Documentation

### API docs

- [Scenario API Docs](https://docs.scenario.com/docs/welcome-to-the-scenario-api)
- [OpenAPI Spec](https://cdn.cloud.scenario.com/static/api/swagger.yaml)
- [API Reference](https://docs.scenario.com/reference)

### MCP docs

- [Scenario MCP run_model](https://mcp.scenario.com/docs/tools/run-model)
- [Scenario MCP display_asset](https://mcp.scenario.com/docs/tools/display-asset)
- [Scenario MCP recommend](https://mcp.scenario.com/docs/tools/recommend)
