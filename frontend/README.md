# ARC Web

Temporary scaffolding for the ARC web interface.

## Commands

```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # TypeScript check plus production build
npm run lint     # ESLint
npm run format:check  # Prettier check
```

The dev server proxies `/api` to `http://localhost:8000`. Set
`VITE_ARC_API_URL` to point elsewhere when needed.
