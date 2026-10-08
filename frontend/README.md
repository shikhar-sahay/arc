# ARC Web

React observation and contract-management interface for ARC.

## Commands

```bash
npm install
npm run dev      # Vite dev server on http://localhost:5173
npm run build    # TypeScript check plus production build
npm run lint     # ESLint
npm run format:check  # Prettier check
```

The dev server proxies `/api` and `/ws` to `http://localhost:8000`. Set
`VITE_ARC_API_URL` to another backend origin when needed. The same origin
is used for REST and WebSocket connections. When the frontend itself is
served from another origin, add it to the backend's comma-separated
`ARC_CORS_ORIGINS` setting.
