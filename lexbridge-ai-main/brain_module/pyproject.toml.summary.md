# File: pyproject.toml

## Purpose
Configures the project's build system, dependencies, and tool settings for the "brain_module" project.

## Key Components
### Project Metadata
* `name`: The project name is set to `"brain_module"`.
* `version`: The project version is set to `"0.1.0"`.
* `description`: A brief description of the project.
* `requires-python`: Specifies that Python 3.10 or higher is required.

### Dependencies
The project has several dependencies, categorized by purpose:
* **Retrieval/Reranking**: sentence-transformers (2.6.1), torch (2.2.2)
* **LightRAG Client**: httpx (0.27.0), aiohttp (3.9.5)
* **API**: fastapi (0.111.0), uvicorn (0.30.0), sse-starlette (2.1.0)
* **LLM Clients**: openai (1.35.0), litellm (1.40.0)
* **Schema/Utilities**: langdetect (1.0.9), pydantic (2.7.0), tenacity (8.3.0), python-dotenv (1.0.0)
* **Caching**: redis (5.0.4)
* **Evaluation**: ragas (0.1.14), datasets (2.19.0), lightrag-hku (1.4.14), pyjwt (2.12.1), bcrypt (5.0.0), ollama (0.6.1), neo4j (6.1.0)
* **External Dependency**: data-module

### Optional Dependencies
The project has two optional dependency groups:
* `dev`: pytest (8.0), pytest-asyncio (0.23), httpx (0.27.0) for development purposes.
* `audio`: openai-whisper (20231117), pydub (0.25.1), edge-tts (7.0) for audio processing.

### Tool Settings
The project configures tool settings:
* `tool.setuptools.packages.find`: Includes the brain_module package and its subpackages.
* `tool.uv.sources`: Specifies the data-module dependency as an editable source in the parent directory (`../data_module`).