# Economy — use Clay, don't buy a second scraper

The company already pays for Clay. Use that first.

```bash
./who-finder rate ~/Downloads/clay-export.csv
```

No Clay API key. Title, company, and size come from the export.

| Use this | Not this |
|---|---|
| Clay table export | Apollo (same job) |
| `yt-dlp` on a YouTube URL | ScrapeCreators for video |
| `find` / DuckDuckGo | a paid search just to get names |
| Bright Data | only if LinkedIn post counts are still missing |

`--cheap` on `find` or `run` skips a new invoice.

Clay tells you **who they are**. It does not tell you how their posts perform. A price needs posts (yt-dlp, a posts CSV, or Bright Data).
