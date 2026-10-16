# YouTube clip processor

POST /clip with JSON `{ "videoId": "jNQXAC9IVRw", "start": 2, "end": 5 }`.
Returns a silent H.264 MP4 containing the selected segment. The browser then adds the Hebrew caption, encodes a GIF and uses the existing file share handler.

Build this directory as a Docker service with outbound HTTPS and at least 512 MB RAM. Expose PORT (default 8080) behind HTTPS. Set SITE_ORIGIN to the exact frontend origin. GET /health is the readiness endpoint. No provider keys or browser cookies are required. Private, age-restricted, DRM, unavailable videos and upstream blocks are reported as failures; they are not bypassed.

Two concurrent jobs; five requests per minute per direct peer IP; bounded duration, file size, subprocess timeout, temporary directory cleanup, exact CORS origin. Behind a reverse proxy, configure edge IP rate limiting too (the service deliberately does not trust caller-controlled forwarding headers). Keep only one instance unless a shared rate limiter is added. Container resource/disk limits must be set by the host.

Deployment remains pending. No service URL has been provisioned and no successful live YouTube extraction has yet been verified. Do not enable the UI until the live clip endpoint passes a real extraction test.

After the live endpoint passes verification, configure the frontend head with:
`<meta name="youtube-clip-endpoint" content="https://PROCESSOR-HOST/clip">`.
The editor downloads the marked clip, feeds it into the existing local caption/GIF encoder, and preserves the synchronous Web Share file flow. No endpoint is configured until deployment is complete.

Local extraction test on 2026-10-16: metadata for `jNQXAC9IVRw` succeeded, but media download failed with `Invalid data found when processing input` in FFmpeg. This is not a successful end-to-end YouTube test. Browser QA remains pending.
