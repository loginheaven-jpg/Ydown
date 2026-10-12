# YDown development instructions

## Planning documents and current scope

- Keep every unimplemented feature, proposal, design decision, and future task in the root `plan.md`. Other documents should link to it rather than duplicate plans. README.md describes implemented behavior and verification results.
- The current Phase 2 request is design-only: preserve Phase 1 and describe adding online extraction using the always-on Windows PC. Do not implement Phase 2, change deployment/network settings, or create permanent background services without a subsequent implementation request.

## Deployment feasibility and verification

- Before recommending a hosting platform or claiming the app works on the web, explain that YouTube may require authentication or reject requests from the hosting network. Local success does not establish cloud feasibility.
- Verify a permitted representative video on the actual target deployment through the complete flow: browser input, progress connection, source download, audio conversion, and saving the resulting playable file. Server health, a successful build, UI rendering, or mocked tests alone do not establish extraction success.
- Report infrastructure health and extraction success separately. Record the tested environment, date, extraction engine, outcome, and any remaining dependency before recommending wider rollout.
- As of 2026-10-12, Railway extraction failed with YouTube's bot authentication response on stable and nightly yt-dlp; the local Windows bundle extracted the same test video successfully. Treat Windows as the verified distribution path until new target-environment evidence changes this finding. Local success is a tested result, not a guarantee for every PC or future YouTube behavior.
- Do not collect or upload browser login cookies automatically. A cloud cookie experiment requires the user's explicit authorization for the specific session data and destination. Do not promise that cookies or changing hosting platforms will resolve the failure.
