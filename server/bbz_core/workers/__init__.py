"""Background workers (dispatchers, housekeeping).

Each worker is safe to start on every node; cluster-wide single execution is
provided by the etcd-lease leader election (E04-08). Until then a single dev
node runs them directly.
"""
