# Matchroom

AI match desk for the **Inside the Game: Developer Hackathon** (Microsoft x Premier League).
Turns a live stream of synthetic football events into explainable match intelligence,
real-time narratives, automated recaps and personalised fan experiences.

> **All data is synthetic.** Clubs, players, venue and results are fictional.
> No real Premier League data, names or logos are used.

## Pipeline

Ingest → Interpret → Explain → Render → Personalize

| Stage | Status |
|---|---|
| Ingest: synthetic match event generator | done |
| Interpret: live stats, momentum, control-vs-chaos | done |
| Explain: key moments with evidence, multi-agent narration | in progress |
| Render: timed overlay output | planned |
| Personalize: fan profiles, English and Swahili | planned |

## Quick start

Requires Python 3.10+. No dependencies yet.

```
python scripts/generate_match.py --seed 7
```

This writes `data/synthetic/match_007.json` and prints a summary.

## License

MIT License

Copyright (c) 2026 Njenga Evans

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
