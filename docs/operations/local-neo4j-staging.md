# Local Neo4j staging operations

The Phase 3 external holdings bundle is loaded into a disposable local Neo4j
Community container before any remote write. The current runtime uses Colima,
Docker CLI, and container `mirae-neo4j-staging`.

## Start

```bash
colima start
docker start mirae-neo4j-staging
docker ps --filter name=mirae-neo4j-staging
```

Wait until the database accepts Bolt connections. The configured endpoints are:

- Neo4j Browser: <http://127.0.0.1:17474>
- Bolt: `neo4j://127.0.0.1:17687`
- Database: `neo4j`
- User: `neo4j`

The generated local password and staging pins are stored only in the git-ignored
`.env`; do not paste them into chat or commit them. Runtime container
authentication is stored in git-ignored `var/neo4j-staging.env`.

## Verify and load

```bash
uv run mirae-ingest verify-collection \
  --targets config/ingest/phase3/nport_targets.json \
  --crosswalk data/crosswalks/contest_entities.csv \
  --raw-root var/ingest/raw \
  --normalized-root var/ingest/normalized \
  --manifest-root var/ingest/manifests

uv run mirae-ingest load \
  --targets config/ingest/phase3/nport_targets.json \
  --crosswalk data/crosswalks/contest_entities.csv \
  --raw-root var/ingest/raw \
  --normalized-root var/ingest/normalized \
  --manifest-root var/ingest/manifests \
  --environment staging \
  --expected-database neo4j \
  --authorize-write
```

The second load should report zero loaded rows and one skipped batch for the
current KSTR bundle. The staging receipt is retained at
`var/ingest/receipts/staging.json`.

## Stop and restart

Stop only Neo4j while leaving Colima running:

```bash
docker stop mirae-neo4j-staging
```

Stop the entire local Docker VM:

```bash
docker stop mirae-neo4j-staging
colima stop
```

After `colima start`, run `docker start mirae-neo4j-staging` again. Container
data survives stop/start but is disposable and will be lost if the container is
removed. Do not run `docker rm` unless staging data is intentionally discarded.

## Later Yeongmin load

The raw, normalized, manifest, and receipt digests are destination-independent,
and graph URIs are deterministic. The same verified bundle can therefore be
loaded into Yeongmin's Neo4j after a production gate is implemented that binds
the exact local staging receipt to an explicitly approved remote URI and
database. The current CLI intentionally blocks production loading; do not
relabel the remote database as staging to bypass that control.
