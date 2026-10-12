# YDown development instructions

## Deployment feasibility and verification

- Before recommending a hosting platform or claiming the app works on the web, explain that YouTube may require authentication or reject requests from the hosting network. Local success does not establish cloud feasibility.
- Verify a permitted representative video on the actual target deployment through the complete flow: browser input, progress connection, source download, audio conversion, and saving the resulting playable file. Server health, a successful build, UI rendering, or mocked tests alone do not establish extraction success.
- Report infrastructure health and extraction success separately. Record the tested environment, date, extraction engine, outcome, and any remaining dependency before recommending wider rollout.
- As of 2026-10-12, Railway extraction failed with YouTube's bot authentication response on stable and nightly yt-dlp; the local Windows bundle extracted the same test video successfully. Treat Windows as the verified distribution path until new target-environment evidence changes this finding. Local success is a tested result, not a guarantee for every PC or future YouTube behavior.
- Do not collect or upload browser login cookies automatically. A cloud cookie experiment requires the user's explicit authorization for the specific session data and destination. Do not promise that cookies or changing hosting platforms will resolve the failure.
