# File: run_frontend.sh

## Purpose
Run the frontend application using Vite and React.

## Key Components
- Uses `pnpm` as package manager.
- Deploys to `http://localhost:5173`.
- References `VITE_API_BASE_URL` environment variable for API base URL.

## Important Logic
- Installs dependencies with `pnpm install` if `node_modules` directory does not exist.
- Runs frontend development mode using `pnpm dev`.

## Dependencies
- Requires `bash`, `env`, and `pnpm` to be installed on the system.
- Assumes project structure: `run_frontend.sh` is in a parent directory of `frontend/`.

## Notes
- This script assumes it is being run from the root of the project. If not, you may need to adjust the paths accordingly.