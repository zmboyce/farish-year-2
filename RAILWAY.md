# Railway deployment

1. **Start command** (see `railway.toml`) runs `python serve_dashboard.py`, which serves this directory and supports optional HTTP Basic Auth.

2. In the Railway project, add **Variables**:
   - `BASIC_AUTH_USER` — dashboard login username  
   - `BASIC_AUTH_PASSWORD` — dashboard login password  
   (Do not commit real values; set them only in Railway.)

3. `PORT` is set automatically by Railway. Optional: `HTTP_SERVER_ROOT` (defaults to `.`).

4. After deploy, open `/farish_dashboard.html` (or set a redirect from `/` in your app if you add one later).

## Git remotes (example)

```bash
git remote add capa https://github.com/capa-strategies/farish-year-2.git
git push -u capa main
```
