# CJK subtitle policy: publish and enable

This is a writable fork of [Dictionarry-Hub/database](https://github.com/Dictionarry-Hub/database),
based on branch `v2`, commit `acc3e2a5fd1b4bd147806317a662f2b4a5d08943`.
The local branch is `cjk`. All 386 upstream SQL operations are unchanged;
`ops/900000.cjk-chinese-subtitles.sql` adds the local policy after them.

The repository has been prepared locally. Nothing has been published, deployed,
or changed in the live Arr, Prowlarr, Profilarr or Seerr settings.

## What changes

| Item | Behavior |
| --- | --- |
| `CJK 2160p Quality - Chinese Subs` | Copies upstream `2160p Quality`, then requires Chinese subtitle evidence. Retains its permitted qualities, grouping, language, quality scores, minimum score and upgrade rules. |
| `CJKSub` | Any explicit Chinese subtitle claim: +1. |
| `CJKSubS` | Simplified claim: +2,000. |
| `CJKSubT` | Traditional claim: +1. |
| Missing-evidence format | Rejects unknown or explicitly contradictory subtitle claims. |
| `CJK Immediate` | Torrent-only, zero-minute delay; separately selected for the 中文 instances. |

Traditional and unspecified-script Chinese subtitles are acceptable. A Simplified
claim adds a preference within the existing quality/scoring system; it does not
override every upstream quality distinction. Upgrades still obey the upstream
cutoff and upgrade rules. Downloading immediately means a later Simplified release
may arrive after a Traditional release has already downloaded.

The rejection penalty is calculated as minus the sum of **all positive scores
plus one**, separately for each Arr. At this revision it is -22,337,324 for Radarr
and -19,512,334 for Sonarr. Even the theoretical maximum of every positive bonus
cannot cancel it. A conventional -10,000 penalty would be ineffective against
Dictionarry's much larger tier scores. Do not add independent score overrides
after this operation without recalculating and testing the bound.

## Why the adapter is included

Arr custom formats inspect release titles and filenames. They do not score
Prowlarr's Torznab description text. The adapter reads that description and adds
`CJKSubS`, `CJKSubT` or `CJKSubU` to the title, before the release group. Explicit
negative claims produce `CJKSubNO`, which vetoes the positive formats.

It recognizes explicit claims such as CHS, CHT, 简繁英字幕, 中文字幕, and
“Simplified Chinese subtitles.” Chinese audio, Chinese characters in the title,
MULTI, DUAL, language=Chinese and release-group reputation are insufficient.
It does not inspect torrent payloads, scrape detail pages, acquire subtitles,
or prove that a tracker's claim is correct. Unrecognized wording remains unknown.

The six observed Doctor X S01E06 results are included as sanitized test fixtures.
Only SpringSunday's CMCTV result explicitly claimed Chinese subtitles, in its
description: `[简繁英字幕]`. That result passes the evidence rule. The other five
remain unknown; this does not prove they lack subtitles. Other quality, seed,
queue and upgrade checks can still reject a release that passes this rule.

## 1. Publish the local branch to Gitea

Create an ordinary writable repository at
`http://mac.local:3000/mike/profilar_profiles` if it does not already exist.
Use an empty repository without an initial README for the simplest first push.
Do not configure it as an automatic pull mirror: the customized branch needs
to retain local commits.

The supplied checkout already has `upstream` pointing to GitHub and `origin`
pointing to Gitea. From the repository folder:

```sh
git push -u origin cjk
```

Set Gitea's default branch to `cjk`. Use normal Git authentication when prompted;
never put access tokens into this repository. No force push is needed.

If moving the supplied bundle to another machine, restore it with:

```sh
git clone -b cjk profilar_profiles.bundle profilar_profiles
cd profilar_profiles
git remote set-url origin http://mac.local:3000/mike/profilar_profiles.git
git remote add upstream https://github.com/Dictionarry-Hub/database.git
git push -u origin cjk
```

## 2. Deploy the description adapter

On a Docker host reachable by both 中文 Arr instances, copy/clone this repository
and run:

```sh
cd cjk
docker compose up -d --build
```

The default upstream is `http://10.0.6.59:9696`. The default allowed indexer IDs
are `1,10,11,12,13`: M-Team, Audiences, HDSky, PTerClub and SpringSunday.
Override `PROWLARR_URL` or `CJK_INDEXER_IDS` in a local `.env` if necessary.
The service listens on port 9697; `/health` returns `ok`.

Existing Arr indexer API keys are forwarded to Prowlarr per request. No key is
stored in the adapter configuration. The service only accepts capabilities,
RSS/search, TV-search and movie-search requests for the allowed IDs. Download
links continue to point directly to Prowlarr. Keep the adapter on the same
trusted network as these services; feed requests contain the Prowlarr key.

### Route the 中文 feeds through it

1. In Prowlarr, change **only Radarr 中文 and Sonarr 中文** application sync levels
   from **Full Sync** to **Add and Remove Only**. Keep their existing tags.
2. In each 中文 Arr, edit the existing five Torznab indexers. Replace the server
   portion of each URL with the adapter's reachable address, preserving its ID.
   For example, SpringSunday changes from `http://10.0.6.59:9696/13/` to
   `http://YOUR_ADAPTER_HOST:9697/13/`. Keep API Path `/api` and the existing key.
3. Test each indexer and save it. Review any newly added/re-created indexer later:
   Add and Remove Only can create new entries with Prowlarr's original URL.
4. Keep both Global applications and their feed URLs as they are.

Prowlarr Full Sync would overwrite manually changed indexer settings on a
subsequent sync. See its [official application settings](https://wiki.servarr.com/prowlarr/settings#application-settings).
The adapter intentionally does not implement Prowlarr's management API; do not
replace Prowlarr's own application-level server URL with the adapter address.

## 3. Select the fork and profile in Profilarr

Add the Gitea repository URL with branch **`cjk`**, and let Profilarr pull/compile
it. Prefer adding this as a separate database for the 中文 instances while leaving
the Global instances on their current database and profile selections. If you
replace the existing database instead, review the proposed sync changes first:
this checkout is a newer upstream snapshot than some live settings observed
during the audit.

Sync **CJK 2160p Quality - Chinese Subs** and its referenced custom formats to
Radarr 中文 and Sonarr 中文. Under delay-profile synchronization select
**CJK Immediate** for those two instances if you want zero delay maintained by
Profilarr. Merely importing the database does not select or apply that preset.
The stock upstream delay presets remain 360 minutes. That waiting window gives
better releases time to arrive; it is not an estimate of download duration.

Start by assigning the new quality profile to Doctor X or another pilot title.
Then set it as Seerr's default quality profile for the corresponding 中文 servers
for new requests. Existing titles retain their assigned profiles until changed;
review the `Any` exception separately instead of bulk-overwriting everything.

Enable a naming template that includes **`{Custom Formats}`** and retains the
new positive formats. Upstream's current Sonarr template already includes that
token, but check the actual live template and any format-name filters. The
`CJKSub`, `CJKSubS` and `CJKSubT` names are deliberately recognizable on later
filename scans. Test one actual import and rescan before broad rollout.

Existing files without these markers may rescore as unknown even if their
embedded subtitle metadata says `chi`. Do not trigger a library-wide search
or bulk rename during initial rollout. Inspect existing subtitles and preserve
evidence deliberately; `chi` alone does not identify Simplified vs Traditional.

## 4. Check the pilot

Use Interactive Search for Doctor X S01E06 after routing the feed and assigning
the profile. Confirm the CMCTV title receives `CJKSubS.CJKSubT`, its group remains
CMCTV, and the new custom formats match. Confirm unknown releases receive the
large missing-evidence penalty. Inspect remaining rejection reasons separately.

The original episode investigation also found queued E01/E02 downloads whose
generic S01 names were interpreted as season packs, and a six-hour delay at that
time. A profile change does not repair stale queue/history entries. Verify the
actual torrent contents and their intended episodes before correcting/removing
stale entries. The later live audit showed zero delay already, so six hours is
not necessarily a current blocker.

If the pilot fails, restore its previous quality profile and the original
Prowlarr URLs, then restore Full Sync for the 中文 apps. Keeping the original
profiles makes rollback straightforward. This repository does not delete media.

## Validation and maintenance

From the repository root with Python 3.12+:

```sh
python -m cjk.build_policy --check
python -m unittest cjk.test_policy -v
```

On Windows, verify the actual .NET regex engine too:

```powershell
./cjk/check_dotnet.ps1 -Python python
```

Validated on 2026-10-25: 19 tests passed, with full schema + 387-operation
database replay, foreign-key/integrity checks, preservation of every upstream
row, score bounds, XML invariance and local HTTP integration tests. All 117
.NET regex cases passed. A read-only live Sonarr 4.0.20 parse check preserved
Doctor X S01E06, WEBDL-1080p and group CMCTV without adding a Chinese audio claim.
Profilarr 2.3.1's operation ordering and score-export source were inspected.
Docker deployment, live Profilarr sync, Radarr runtime parsing and a real
download/import/rescan have **not** been performed.

For upstream updates:

```sh
git fetch upstream
git switch cjk
git merge upstream/v2
python -m cjk.build_policy --check
python -m unittest cjk.test_policy -v
git push origin cjk
```

Review changes before pushing; do not schedule blind upstream merges. The local
SQL copies the final upstream base profile at compile time and recomputes its
rejection bound. Keep local operation numbers at 900000 or above, and check for
new upstream name/schema conflicts. If subtitle wording rules change, update
`cjk/policy.json` / `cjk/evidence.py`, regenerate with `python -m cjk.build_policy`,
and add cases before committing. Rebuild/redeploy the adapter with the same
revision so its evidence policy matches the database.
