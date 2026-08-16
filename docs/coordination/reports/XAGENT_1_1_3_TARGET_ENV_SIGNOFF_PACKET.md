# X-Agent v1.1.3 Target Environment Signoff Packet

This packet is intentionally incomplete until every evidence file exists for the
same source SHA and the named owners approve the target environment release.

- Release ID: TBD
- Source SHA: TBD
- Environment: TBD
- Explicit authorization: TBD
- Hosted CI evidence: TBD | sha256=TBD
- Paid model evidence: TBD | sha256=TBD
- Signed desktop evidence: TBD | sha256=TBD
- Backup evidence: TBD | sha256=TBD
- Migration evidence: TBD | sha256=TBD
- Health evidence: TBD | sha256=TBD
- Browser evidence: TBD | sha256=TBD
- Rollback evidence: TBD | sha256=TBD
- TL signoff: TBD
- QA signoff: TBD
- DevOps signoff: TBD
- Owner signoff: TBD
- Final disposition: blocked

Each evidence value must use `relative/path | sha256=<64 lowercase hex>` and
resolve beneath the supplied evidence root. Each referenced file must be a JSON
object whose `source_sha` equals the packet SHA. Run the gate only after
replacing all placeholders:

```text
python scripts/target_env_release_gate.py --packet packet.md \
  --evidence-root evidence \
  --source-sha <40-character-git-sha> \
  --output target-env-evidence.json
```
