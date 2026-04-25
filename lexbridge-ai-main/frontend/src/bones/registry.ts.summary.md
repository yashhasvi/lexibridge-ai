# File: registry.ts

## Purpose
Registers bones for React components using the Boneyard library.

## Key Components
- `import { registerBones } from "boneyard-js/react";`: Imports the `registerBones` function from the Boneyard library.
- `{}`: An empty object passed to `registerBones`, indicating a placeholder registry that will be replaced after running the `npx boneyard-js build` command.

## Important Logic
The file temporarily registers an empty bone map until the generated bone maps are imported after building with `boneyard-js`.

## Dependencies
- Boneyard library (`boneyard-js/react`)

## Notes
After running the `npx boneyard-js build` command, replace the placeholder registry with the generated bone maps.