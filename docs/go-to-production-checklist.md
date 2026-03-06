# TotalReclaw -- Go-to-Production Checklist

## A. Deployment
- [ ] Verify Railway health check path is `/health` (not full URL)
- [ ] Verify: `curl https://api.totalreclaw.xyz/health` returns 200
- [ ] Connect GitHub repo for auto-deploy on push to main
- [ ] Remove `DEBUG=true` from production env vars

## B. Security
- [ ] Set `CORS_ORIGINS` to `https://totalreclaw.xyz` only
- [ ] Verify deployer wallet private key is NOT in production env
- [ ] Rotate any test API keys used during development
- [ ] Scrub git history: `git log --all -p -S "sk_test"` (no real keys)
- [ ] Review all `.env.example` files for leaked values

## C. GitHub (Going Public)
- [ ] Add LICENSE file
- [ ] Remove hardcoded test credentials from non-test files
- [ ] Verify `.gitignore` blocks `.env`, `credentials.json`, `node_modules`
- [ ] Add branch protection on `main`
- [ ] Add CONTRIBUTING.md

## D. Website
- [ ] Verify `totalreclaw.xyz` landing page is live
- [ ] Add `/pricing` page (referenced in quota error messages)
- [ ] Add `/payment/success` and `/payment/cancel` pages

## E. External Services
- [ ] Stripe: Switch from test mode to live mode
- [ ] Stripe: Verify webhook endpoint registered and delivering
- [ ] Coinbase Commerce: Verify webhook endpoint + merchant wallet
- [ ] Pimlico: Verify API key works on Chiado
- [ ] Graph Studio: Verify subgraph is synced and serving queries

## F. Documentation
- [ ] Beta tester guide updated and validated by E2E tests
- [ ] `docs/deployment/env-vars-checklist.md` complete
- [ ] CHANGELOG.md up to date

## G. ClawHub Publishing
- [ ] Create 3-5 screenshots (1920x1080 PNG) -- agent remembering, recalling, exporting
- [ ] Create 256x256 skill icon (transparent background)
- [ ] Record 30-90 second demo video (optional but recommended)
- [ ] Publish npm package: `@totalreclaw/skill`
- [ ] Run `clawhub validate ./skill`
- [ ] Run `clawhub publish ./skill --slug totalreclaw`
- [ ] Verify listing at clawhub.ai/skills/totalreclaw
