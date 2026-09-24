# ScribeBench web

React + Vite review interface. During local development, Vite proxies `/api` to `127.0.0.1:8000`. The container uses Nginx as the same-origin reverse proxy and injects the optional service API key without placing it in the JavaScript bundle.

```bash
npm install
npm run dev
```

