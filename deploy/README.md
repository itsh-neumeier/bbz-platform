# deploy/

Deployment topology assets. **Phase 0 provides documentation and stubs only** —
the HA stack (PostgreSQL + Patroni + 3× etcd/Consul + 2 app nodes) is wired in
Phase 2 (ADR-0001, ADR-0018).

```
deploy/
  compose/         per-node stack: bbz-api, bbz-web, postgres, patroni, etcd, reverse-proxy
  patroni/         Patroni configuration templates
  etcd/            distributed config store (3 voting members incl. witness)
  reverse-proxy/   TLS termination, security headers, CSP
  quorum/          BBZ-QUORUM01: etcd/Consul third member ONLY — no BBZ domain logic
```

The root `docker-compose.yml` is the developer convenience stack (single node,
`core` profile). Production per-node composition lives here and is built out in
Phase 2.
